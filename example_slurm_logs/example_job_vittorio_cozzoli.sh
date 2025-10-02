#!/bin/bash -l

#SBATCH --job-name=example_job_vittorio_cozzoli
#SBATCH --time=00:05:00
#SBATCH --qos=default
#SBATCH --partition=gpu
#SBATCH --account=p200981                      
#SBATCH --nodes=1                          
#SBATCH --ntasks=1                        
#SBATCH --ntasks-per-node=1              
#SBATCH --output=example_job_vittorio_cozzoli_%j.out
#SBATCH --error=example_job_vittorio_cozzoli_%j.err


# Load the env
module add Apptainer

# Run the processing
apptainer pull docker://ollama/ollama
apptainer exec --nv ollama_latest.sif ollama serve

# Final debug string: print job id, host and timestamp when the service exits
echo "[DEBUG] Job $SLURM_JOB_ID finished on $(hostname) at $(date '+%Y-%m-%d %H:%M:%S')"