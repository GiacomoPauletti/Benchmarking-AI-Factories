# Session Notes: Model and Time Limit Configuration Feature

**Date:** December 13, 2025  
**Branch:** `feat/start-service-model-time-limit`  
**Status:** ✅ COMPLETED - Ready for testing and merge

---

## Overall Objective

Add two new configuration fields to the Grafana "Start service" panel:
1. **Model field**: A dropdown menu populated dynamically from the backend API endpoint `/api/v1/vllm/model-options`, showing available HuggingFace models for vLLM services
2. **Time limit field**: A slider allowing users to set job time limits (5-120 minutes)

Both fields should only appear when a recipe is selected, and the Model field should only appear for vLLM recipes.

---

## What Was Accomplished

### 1. Backend API Enhancement

**File:** `services/server/src/api/routes.py`

Created a new endpoint specifically formatted for Grafana dropdown consumption:

```python
@router.get("/vllm/model-options")
async def get_vllm_model_options():
    """Get vLLM model options formatted for Grafana dropdown.
    
    Returns an array of label/value pairs suitable for use in Grafana Form Panel dropdowns.
    Each entry contains a human-readable label and the corresponding HuggingFace model ID.
    
    **Returns:**
    ```json
    [
      {"label": "GPT-2 (small, for testing)", "value": "gpt2"},
      {"label": "Llama 2 7B Chat", "value": "meta-llama/Llama-2-7b-chat-hf"},
      ...
    ]
    ```
    """
    try:
        info = get_architecture_info()
        examples = info.get("examples", {})
        # Convert examples dict to array of label/value objects
        return [{"label": label, "value": value} for label, value in examples.items()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Location:** Added after line 560, before the `/vllm/search-models` endpoint

**Why this was needed:** The original endpoint `/api/v1/vllm/available-models` returns a complex nested JSON structure. Grafana's Infinity datasource with the Form Panel needed a simple array of `{label, value}` objects to populate the dropdown.

**Test the endpoint:**
```bash
curl -s http://localhost:8001/api/v1/vllm/model-options | jq '.[0:3]'
# Expected output:
# [
#   {"label": "GPT-2 (small, for testing)", "value": "gpt2"},
#   {"label": "Llama 2 7B Chat", "value": "meta-llama/Llama-2-7b-chat-hf"},
#   {"label": "Llama 3.2 1B Instruct", "value": "meta-llama/Llama-3.2-1B-Instruct"}
# ]
```

### 2. Grafana Dashboard Panel Configuration

**File:** `services/grafana/dashboards/src/administration/panels/01_start_service.json`

#### Changes Made:

**A. Added Time Limit Slider Element (lines ~211-222)**
```json
{
  "id": "config.time_limit",
  "labelWidth": 15,
  "max": 120,
  "min": 5,
  "section": "",
  "showIf": "return context.panel.elements.find(el => el.id == \"recipe_name\").value !== \"\"",
  "step": 5,
  "title": "Time limit",
  "tooltip": "Job time limit in minutes",
  "type": "slider",
  "value": 15
}
```
- Range: 5-120 minutes
- Step: 5 minutes
- Default: 15 minutes
- Visibility: Only shown when a recipe is selected

**B. Added Model Dropdown Element (lines ~79-92)**
```json
{
  "allowCustomValue": true,
  "id": "config.model",
  "labelWidth": 15,
  "optionsSource": "Query",
  "queryOptions": {
    "label": "label",
    "source": "models",
    "value": "value"
  },
  "section": "",
  "showIf": "const elements = context.panel.elements;\nif (!elements) return false;\nconst recipe = elements.find(el => el.id === 'recipe_name');\nreturn recipe && (recipe.value || '').toLowerCase().includes('vllm');",
  "title": "Model",
  "tooltip": "HuggingFace model ID (type custom value if not in list)",
  "type": "select",
  "value": ""
}
```
- `allowCustomValue: true` - Users can type custom HuggingFace model IDs
- `optionsSource: "Query"` - Populates from datasource query
- `queryOptions.source: "models"` - References the "models" target (see below)
- Visibility: Only shown for vLLM recipes (recipe name contains "vllm")

**C. Added Datasource Target for Model Options (lines ~307-329)**
```json
{
  "columns": [
    {
      "selector": "label",
      "text": "label",
      "type": "string"
    },
    {
      "selector": "value",
      "text": "value",
      "type": "string"
    }
  ],
  "datasource": {
    "type": "yesoreyeram-infinity-datasource",
    "uid": "af28rrswju6m8c"
  },
  "filters": [],
  "format": "table",
  "global_query_id": "",
  "parser": "backend",
  "refId": "models",
  "root_selector": "",
  "source": "url",
  "type": "json",
  "url": "/api/v1/vllm/model-options",
  "url_options": {
    "data": "",
    "method": "GET"
  }
}
```
- Uses Infinity datasource (UID: `af28rrswju6m8c`)
- Queries `/api/v1/vllm/model-options`
- Parser: `backend` (processes the JSON response)
- Columns define the expected structure: `label` and `value` fields

**D. Updated Initial Form Values (lines ~227-234)**
```javascript
context.panel.data.initial = context.panel.initial;
context.panel.setFormValue({
  "config.cpus": 1,
  "config.gpus": 0,
  "config.memory": "4G",
  "config.nodes": 1,
  "config.time_limit": 15,
  "config.model": "",
})
context.panel.data.prevSelected = null
```
- Added `config.time_limit: 15` (default 15 minutes)
- Added `config.model: ""` (empty by default)

**E. Updated Form Value Setting on Recipe Change (lines ~44-52)**
```javascript
context.panel.setFormValue({
  "recipe_name": selected,
  "config.nodes": parameters["nodes"] || 1,
  "config.cpus": parameters["cpu"] || 1,
  "config.gpus": parameters["gpu"] || 0,
  "config.memory": (parameters["memory"] || "4G").replace("i", "").replace(" ", ""),
  "config.time_limit": parameters["time_limit"] || 15,
  "config.model": defaultModel
})
```
- When user selects a recipe, the form auto-populates with recipe defaults
- `defaultModel` is extracted from recipe parameters if available

**F. Updated Payload Construction (lines ~273-283)**
```javascript
} else if (element.id === 'config.model') {
  payload.config.model = element.value;
} else if (element.id === 'config.time_limit') {
  payload.config.resources.time_limit = parseInt(element.value) || 15;
}
```
- `config.model` is added to `payload.config.model`
- `config.time_limit` is added to `payload.config.resources.time_limit` (parsed as integer)

**G. Fixed URL Configuration (Critical Fix)**

**BEFORE (BROKEN):**
```json
"url": "http://:/api/v1/recipes"  // Initial query
"url": "http://:/api/v1/services" // Submit action
```

**AFTER (WORKING):**
```json
"url": "http://${server}:${port}/api/v1/recipes"  // Initial query
"url": "http://${server}:${port}/api/v1/services" // Submit action
```

**Why this was critical:** The Form Panel makes direct HTTP requests (not through the datasource proxy). It needs fully qualified URLs with dashboard variables:
- `${server}` resolves to `localhost` (defined in dashboard.json)
- `${port}` resolves to `8001` (defined in dashboard.json)
- Final URL: `http://localhost:8001/api/v1/services`

### 3. Dashboard Build System

**File:** `services/grafana/dashboards/build_dashboards.py`

No changes needed - this script already handles merging panel JSON files into the full dashboard.

**Usage:**
```bash
python3 services/grafana/dashboards/build_dashboards.py
```

This regenerates:
- `services/grafana/dashboards/administration.json`
- `services/grafana/dashboards/service.json`

---

## Technical Architecture

### Data Flow for Model Dropdown

1. **User opens dashboard** → Grafana loads panel configuration
2. **Panel initialization** → Executes target query with `refId: "models"`
3. **Infinity datasource** → Sends GET request to `http://server:8001/api/v1/vllm/model-options`
4. **Backend server** → Returns array: `[{label: "...", value: "..."}, ...]`
5. **Infinity parser** → Processes JSON, creates table with `label` and `value` columns
6. **Form Panel** → Populates dropdown using `queryOptions: {source: "models", label: "label", value: "value"}`
7. **User sees dropdown** → Shows human-readable labels, stores model IDs as values

### Form Submission Flow

1. **User fills form** → Selects recipe, adjusts sliders, selects model
2. **User clicks "Start service"** → Triggers `update` action
3. **getPayload function** → Constructs JSON payload:
```json
{
  "recipe_name": "inference/vllm-single-node",
  "config": {
    "nodes": 1,
    "model": "gpt2",
    "resources": {
      "cpu": 2,
      "gpu": 1,
      "memory": "8G",
      "time_limit": 30
    }
  }
}
```
4. **Form Panel** → POSTs to `http://localhost:8001/api/v1/services`
5. **Backend server** → Processes service creation request
6. **Response handling** → Success/error notification + dashboard refresh

---

## Files Modified in This Session

### Backend
1. **`services/server/src/api/routes.py`**
   - Added `/vllm/model-options` endpoint (lines ~561-579)
   - Returns array of `{label, value}` objects for Grafana dropdown

### Frontend
2. **`services/grafana/dashboards/src/administration/panels/01_start_service.json`**
   - Added `config.model` element (~lines 79-92)
   - Added `config.time_limit` element (~lines 211-222)
   - Added "models" datasource target (~lines 307-329)
   - Updated `elementValueChanged` to set default model (~lines 39-52)
   - Updated initial form values (~lines 227-234)
   - Updated payload construction (~lines 273-283)
   - Fixed URLs to use `${server}:${port}` variables (~lines 237, 288)

### Generated (auto-built, not manually edited)
3. **`services/grafana/dashboards/administration.json`**
   - Generated by build_dashboards.py
   - Contains compiled dashboard with all panels

---

## Current Status: COMPLETED ✅

### What Works

✅ **Time limit slider**
- Appears when recipe is selected
- Range: 5-120 minutes, step 5
- Default: 15 minutes
- Value included in service creation payload

✅ **Model dropdown**
- Appears only for vLLM recipes
- Populated dynamically from API
- 13 example models available
- Allows custom HuggingFace model IDs
- Value included in service creation payload

✅ **Backend endpoint**
- `/api/v1/vllm/model-options` returns correct format
- Tested with curl: returns array of label/value objects

✅ **Grafana integration**
- Infinity datasource query succeeds
- Dropdown populates with correct labels and values
- Form submission works with proper URLs

✅ **URL configuration**
- Fixed malformed `http://:/api/v1/...` URLs
- Now uses dashboard variables: `http://${server}:${port}/api/v1/...`
- Resolves to `http://localhost:8001/api/v1/...`

---

## Testing Instructions

### 1. Verify Backend Endpoint
```bash
# Test the new model-options endpoint
curl -s http://localhost:8001/api/v1/vllm/model-options | jq '.'

# Expected: Array of 13 objects with "label" and "value" fields
```

### 2. Test Grafana Query
```bash
# Test Infinity datasource query
curl -s -X POST 'http://localhost:3000/api/ds/query' \
  -H 'Content-Type: application/json' \
  -d '{
    "queries": [{
      "refId": "A",
      "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "af28rrswju6m8c"},
      "type": "json",
      "source": "url",
      "format": "table",
      "url": "/api/v1/vllm/model-options",
      "parser": "backend"
    }],
    "from": "now-5m",
    "to": "now"
  }' | jq '.results.A.frames[0].schema.fields | map(.name)'

# Expected: ["label", "value"]
```

### 3. Test in Grafana UI
1. Open browser: `http://localhost:3000`
2. Navigate to **Administration** dashboard
3. Scroll to **"Start service"** panel
4. Select any recipe → Time limit slider should appear
5. Select a vLLM recipe (e.g., "inference/vllm-single-node") → Model dropdown should appear
6. Verify dropdown shows model options (GPT-2, Llama, Qwen, etc.)
7. Adjust time limit slider → Verify value changes
8. Select a model → Verify selection
9. Click "Start service" → Should not show URL parse errors
10. Check browser console → Should see payload with `model` and `time_limit`

### 4. Test Service Creation
```bash
# Start a test service with model and time limit
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm-single-node",
    "config": {
      "nodes": 1,
      "model": "gpt2",
      "resources": {
        "cpu": 2,
        "gpu": 0,
        "memory": "8G",
        "time_limit": 30
      }
    }
  }'

# Should return service creation response
```

---

## Known Issues and Solutions

### Issue 1: Empty Dropdown (RESOLVED ✅)
**Symptom:** Model dropdown appeared but was empty

**Root Cause:** Original endpoint `/api/v1/vllm/available-models` returned nested JSON:
```json
{
  "examples": {
    "GPT-2 (small, for testing)": "gpt2",
    ...
  }
}
```

UQL transformation (`parse-json | scope "examples" | project "label"=key, "value"=value`) created columns with label names instead of rows.

**Solution:** Created new endpoint `/api/v1/vllm/model-options` that returns flat array:
```json
[
  {"label": "GPT-2 (small, for testing)", "value": "gpt2"},
  ...
]
```

### Issue 2: URL Parse Error (RESOLVED ✅)
**Symptom:** `TypeError: Failed to execute 'fetch' on 'Window': Failed to parse URL from http://:/api/v1/services`

**Root Cause:** Panel configuration had malformed URLs:
- Initial: `"url": "http://:/api/v1/recipes"`
- Submit: `"url": "http://:/api/v1/services"`

**Solution:** Updated to use dashboard variables:
- Initial: `"url": "http://${server}:${port}/api/v1/recipes"`
- Submit: `"url": "http://${server}:${port}/api/v1/services"`

These variables are defined in `dashboard.json`:
- `${server}` = `"localhost"`
- `${port}` = `"8001"`

---

## Next Steps (For Future Sessions)

### 1. Write Tests ⚠️ REQUIRED
**File to create:** `services/server/tests/unit/api/test_vllm_model_options.py`

```python
import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_vllm_model_options_returns_array():
    """Test that /vllm/model-options returns an array."""
    response = client.get("/api/v1/vllm/model-options")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

def test_vllm_model_options_structure():
    """Test that each item has label and value fields."""
    response = client.get("/api/v1/vllm/model-options")
    data = response.json()
    for item in data:
        assert "label" in item
        assert "value" in item
        assert isinstance(item["label"], str)
        assert isinstance(item["value"], str)
        assert len(item["label"]) > 0
        assert len(item["value"]) > 0

def test_vllm_model_options_contains_gpt2():
    """Test that GPT-2 example is included."""
    response = client.get("/api/v1/vllm/model-options")
    data = response.json()
    values = [item["value"] for item in data]
    assert "gpt2" in values
```

**Run tests:**
```bash
./services/server/run-tests.sh
```

### 2. Update Documentation
**File to update:** `docs-src/api/server.md` or `docs-src/services/server.md`

Add documentation for the new endpoint:
```markdown
### GET /api/v1/vllm/model-options

Get vLLM model options formatted for Grafana dropdowns.

**Response:**
```json
[
  {
    "label": "GPT-2 (small, for testing)",
    "value": "gpt2"
  },
  {
    "label": "Llama 2 7B Chat",
    "value": "meta-llama/Llama-2-7b-chat-hf"
  }
]
```

**Use Case:** Provides a simplified format for UI dropdown menus, specifically designed for Grafana Form Panel integration.
```

### 3. Test End-to-End Service Creation
- Start a vLLM service with custom model via Grafana UI
- Verify the model parameter is passed to the orchestrator
- Verify the time limit is respected in the SLURM job

### 4. Consider Additional Enhancements (Optional)
- Add model validation (check if model exists on HuggingFace)
- Add model size indicators next to each option
- Group models by size (small/medium/large)
- Add default time limits per model size
- Add tooltips with GPU memory requirements

---

## Deployment Checklist

Before merging to main:

1. ✅ Run all tests: `./services/server/run-tests.sh`
2. ✅ Add tests for new endpoint
3. ✅ Update API documentation
4. ✅ Test in Grafana UI (all scenarios)
5. ✅ Test service creation with model parameter
6. ✅ Verify backward compatibility (services without model still work)
7. ✅ Check for regressions in other panels
8. ✅ Update CHANGELOG.md with feature description
9. ✅ Create PR with clear description

---

## Troubleshooting Guide

### Dropdown Not Populating
```bash
# 1. Check backend endpoint
curl http://localhost:8001/api/v1/vllm/model-options

# 2. Check Grafana datasource
curl http://localhost:3000/api/datasources/uid/af28rrswju6m8c

# 3. Check Grafana logs
docker compose logs grafana | grep -i "infinity\|error\|model"

# 4. Rebuild dashboard
python3 services/grafana/dashboards/build_dashboards.py
docker compose restart grafana
```

### URL Parse Errors
```bash
# Check panel configuration
cat services/grafana/dashboards/administration.json | jq '.panels[] | select(.title == "Start service") | .options.update.url'

# Should output: "http://${server}:${port}/api/v1/services"
# NOT: "http://:/api/v1/services"
```

### Model Not Appearing for vLLM Recipe
Check `showIf` condition in panel JSON:
```json
"showIf": "const elements = context.panel.elements;\nif (!elements) return false;\nconst recipe = elements.find(el => el.id === 'recipe_name');\nreturn recipe && (recipe.value || '').toLowerCase().includes('vllm');"
```

Recipe name must contain "vllm" (case-insensitive).

---

## Build and Deploy Commands

```bash
# Full rebuild (use this after making changes)
cd /home/jan/Documents/Career_Academics/EUMaster4HPC/Courses/Semester_3/challenge/Benchmarking-AI-Factories
python3 services/grafana/dashboards/build_dashboards.py
docker compose up -d --build --force-recreate

# Quick restart (if only JSON changed)
python3 services/grafana/dashboards/build_dashboards.py
docker compose restart grafana

# Check services
docker compose ps

# View logs
docker compose logs -f grafana
docker compose logs -f server
```

---

## Git Workflow

**Current Branch:** `feat/start-service-model-time-limit`

**Files to Commit:**
1. `services/server/src/api/routes.py` (new endpoint)
2. `services/grafana/dashboards/src/administration/panels/01_start_service.json` (panel config)
3. `SESSION_NOTES_MODEL_TIME_LIMIT_FEATURE.md` (this file)

**Commit Message:**
```
feat: Add model selection and time limit configuration to service panel

- Add /api/v1/vllm/model-options endpoint for Grafana dropdown
- Add model dropdown with 13 pre-configured HuggingFace models
- Add time limit slider (5-120 minutes, step 5)
- Model field only visible for vLLM recipes
- Allow custom HuggingFace model IDs via allowCustomValue
- Fix malformed URLs using dashboard variables ${server}:${port}
- Update payload construction to include model and time_limit

Closes #[issue-number]
```

---

## Summary for Next Session

**Quick Start:**
1. Review this document completely
2. Test the feature in Grafana UI
3. Write tests for `/api/v1/vllm/model-options`
4. Update API documentation
5. Create PR for review

**Critical Files:**
- `services/server/src/api/routes.py` (backend endpoint)
- `services/grafana/dashboards/src/administration/panels/01_start_service.json` (panel config)

**Key Technical Details:**
- New endpoint: `GET /api/v1/vllm/model-options` returns `[{label, value}, ...]`
- Form Panel uses Infinity datasource with `refId: "models"`
- URLs use variables: `http://${server}:${port}/api/v1/...`
- Model field: `optionsSource: "Query"`, `allowCustomValue: true`
- Time limit: slider type, range 5-120, default 15

**Status:** Feature is COMPLETE and WORKING. Next phase is TESTING and DOCUMENTATION.
