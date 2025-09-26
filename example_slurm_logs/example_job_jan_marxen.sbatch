#!/bin/bash -l
#SBATCH --job-name=example_job_jan_marxen
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --account=p200981
#SBATCH --qos=short
#SBATCH --partition=gpu
#SBATCH --time=00:03:00
#SBATCH --output=example_job_jan_marxen_%j.out
#SBATCH --error=example_job_jan_marxen_%j.err

module add Apptainer
# source /bin/activate

apptainer pull docker://ollama/ollama
apptainer exec --nv ollama_latest.sif ollama serve

# This line will never execute because the above command is blocking (server keeps running)
srun echo "Example completed!"
