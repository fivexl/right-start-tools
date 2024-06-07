#!/bin/zsh

#Simple zsh script to clean .terraform terraform.lock.hcl in every directory of the project, it might be useful when you want to reinitialize terraform in a project

# Base directories to search in
base_dirs=("modules" "organization")

# Loop through base directories
for base_dir in "${base_dirs[@]}"; do
  # Find and delete .terraform directories recursively
  find "$base_dir" -type d -name ".terraform" -print -exec rm -rf {} \;

  # Find and delete .terraform.lock.hcl files recursively
  find "$base_dir" -type f -name ".terraform.lock.hcl" -print -exec rm -f {} \;
done
