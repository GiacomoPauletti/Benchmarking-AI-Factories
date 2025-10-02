#!/usr/bin/env bash

#SBATCH --time=00:15:00
#SBATCH --qos=default
#SBATCH --partition=gpu
#SBATCH --account=p200981                      # Put your project ID
#SBATCH --nodes=1                          # num of nodes
#SBATCH --ntasks=1                         # number of tasks
#SBATCH --ntasks-per-node=1                # number of tasks per node


echo "Date              = $(date)"
echo "Hostname          = $(hostname -s)"
echo "Working Directory = $(pwd)"

module add Apptainer

apptainer pull docker://ollama/ollama
apptainer exec --nv ollama_latest.sif ollama serve
