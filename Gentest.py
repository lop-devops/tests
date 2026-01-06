#!/usr/bin/env python3

"""
Gentest.py
This script runs the WCA_CLI commands and can also generate test code for the patch.

Usage:
    ./Gentest.py PATCH_NAME

Example:
    ./Gentest.py fs-patch

Description:
    - Takes the patch file name as an argument in the same location.
    - User can pass CLI commands to history argument
    - Generates a test code file for the patch using avocado-misc-tests style.
    - Extracts only the relevant Python code (like import statements, function and class blocks)
      from the generated output file and writes it to a final Python file.

Author:
    Tellakula Yeswanth Krishna - yeswanth@ibm.com

"""
import os
import sys
import subprocess
import argparse

patch_file = sys.argv[1]
final_py_file = 'test_'+sys.argv[1]+'.py'
data_file= 'sudocode.txt'
WCA_CLI_PATH = 'wca-api/WCA_CLI'
WCA_CLI_REPO_URL="https://github.ibm.com/code-assistant/wca-api.git"

def run_wca_cli_commands(patch_file, data_file):

    #Check APIKEY exist in enviroment
    if not os.getenv("IAM_APIKEY"):
        print("Error: IAM_APIKEY is not set. Please export it by -> export IAM_APIKEY=your_api_key_here and make sure having  python3.13+ Environment")
        sys.exit(1)
        
    #Ensure WCA_CLI repo exists locally. If not, automatically clone it.
    if not os.path.isdir(WCA_CLI_PATH):
        print("The '{WCA_CLI_PATH}' directory does not exist.")
        print("Cloning repository from {WCA_CLI_REPO_URL}...")
        subprocess.run(["git", "clone", WCA_CLI_REPO_URL])
        print("Repository cloned successfully!")

    #Run WCA_CLI commands to gather explanations and generate test code.
    history = [
        "What specific issues does this patch address",
        "Are there any prerequisites or dependencies for applying this patch"
    ]

    history1 = [
        "generate a python py unitest for the patch using the avocado-misc-tests style",
    ]
    
    for i,prompt in enumerate(history,start=1):
       command = [
        "python", "wca-api/WCA_CLI/wca_cli.py", "prompt", prompt,
        "--source-file", patch_file
       ]
       print(f"Executing {i}: {prompt}")
       subprocess.run(command)
       print("\n")
    
    for i, prompt1 in enumerate(history1, start=1):
       with open(data_file, "w") as outfile:
         command = [
            "python", "wca-api/WCA_CLI/wca_cli.py", "unit-test", "--using", "avacado framework",
            patch_file

         ]
         print(f"Executing {i}: {prompt1}")
         subprocess.run(command, stdout=outfile)
         print("\n")


def extract_python_code(input_file, output_file):
    """
    Extract only Python code (imports, def/class blocks, comments) from the generated file.
    """
    with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
        in_code_block = False
        current_indent_level = None

        for line in infile:
            stripped_line = line.lstrip()

            # Keep import statements at top level
            if stripped_line.startswith('import ') or stripped_line.startswith('from '):
                outfile.write(line)
                continue

            # Start of function or class block
            if stripped_line.startswith('def ') or stripped_line.startswith('class '):
                in_code_block = True
                current_indent_level = len(line) - len(stripped_line)
                outfile.write(line)
                continue

            if in_code_block:
                indent_level = len(line) - len(stripped_line)

                # Keep blank lines and comments
                if not stripped_line or stripped_line.startswith('#'):
                    outfile.write(line)
                    continue

                # If line is still part of block
                if indent_level >= current_indent_level:
                    outfile.write(line)
                else:
                    # Outside block
                    in_code_block = False

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Please export APIKEY it by -> export IAM_APIKEY=your_api_key_here and make sure having  python3.13+ Environment.\n"
            "Have the clone repo: https://github.ibm.com/code-assistant/wca-api.git,If not script handle to clone the Repo.\n"
            "Gentest.py: Execute WCA CLI Prompts about patch and Generate Python test code/unit-test for a patch using WCA_CLI and "
            "extract relevant code to a final Python file.\n\n"
            "Example usage:\n"
            "  ./Gentest.py fs-patch\n"
            "This will create test_fs-patch.py from the WCA_CLI-generated output.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "patch_name",
        help="Patch name or file to process (example: fs-patch)"
    )
    args = parser.parse_args()

    print("Running WCA_CLI commands for patch:",patch_file)
    run_wca_cli_commands(patch_file, data_file)

    print("Extracting Python code from "+data_file+" to "+ final_py_file)
    extract_python_code(data_file, final_py_file)


if __name__ == "__main__":
    main()
