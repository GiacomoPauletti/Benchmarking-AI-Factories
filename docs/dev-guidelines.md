# Microservices Development Guide

## AI Benchmarking Application - Development Reference

### Principles

1. **Single Responsibility**: Each service owns one capability
1. **Decoupled Communication**: Services communicate via well-defined APIs
1. **Data Independence**: Each service manages its own database/storage
1. **Failure Isolation**: Service failures don’t cascade to others
1. **Technology Agnostic**: Choose the best tech stack for each service

### Development Workflow

#### Git Strategy

- **Main Branch**: Production-ready, always deployable, protected
- **Dev Branch**: Integration branch for team collaboration, mirrors main but allows for testing
- **Feature Branches**: `feature/service-name/feature-description` or `feature/issue-number`
- **Pull Request Workflow**:
  1. Feature branch -> Dev (for team integration and testing)
  2. Dev -> Main (for production releases)
- **Branch Protection**: Both main and dev require code review + automated tests

#### CI/CD Pipeline

1. **Build**: Docker image creation and testing
1. **Test**: Unit tests, integration tests
1. **Deploy**: Automated deployment to dev/main

### Team Collaboration

#### Service Ownership

- Each team member owns one primary service (Server, Client, Logs or Monitor). APIs documented and versioned.
- Cross-training sessions for knowledge sharing (every week?)
- Shared responsibility for integration testing

**Remember**: Start simple, iterate fast, and maintain service boundaries. Focus on getting the basics right before optimizing.
