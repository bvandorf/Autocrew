
# filename: autocrew.py
#####################################################################################################################
AUTOCREW_VERSION = "3.1.0"

# Please do not edit this file directly
# Please modify the config file, "config.ini"
# If you experience any errors, please upload the complete log file, "autocrew.log", along with your issue on GitHub:
# https://github.com/yanniedog/autocrew/issues/new 
#####################################################################################################################


import argparse
import configparser
import copy
import csv
import io
import json
import logging
import logging.config
import ollama
import os
import re
import requests
import shutil
import subprocess
import sys
import tiktoken
import time

from logging_config import setup_logging
from core import AutoCrew
from datetime import datetime
from packaging import version
from typing import Any, Dict, List
from ast import literal_eval

from crewai import Agent, Crew, Process, Task
from langchain_community.llms import Ollama
from langchain_community.tools import DuckDuckGoSearchRun
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from openai import OpenAI

GREEK_ALPHABETS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa",
                       "lambda", "mu", "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon"]

def clear_screen():
    # Clear the screen command for different operating systems
    command = 'cls' if os.name == 'nt' else 'clear'
    os.system(command)
        
def log_command_line_arguments():
    logging.info(f"Command-line arguments: {' '.join(sys.argv[1:])}")
    
    
    
def install_dependencies():
    requirements_file = 'requirements.txt'
    if not os.path.exists(requirements_file):
        raise FileNotFoundError(f"{requirements_file} not found in the current working directory.")

    if os.stat(requirements_file).st_size == 0:
        logging.error("The requirements.txt file is empty.")
        raise ValueError("Empty requirements.txt file.")

    pip_executable = shutil.which('pip') or shutil.which('pip3')
    if not pip_executable:
        raise EnvironmentError("pip is not available on the system.")

    logging.info("Installing dependencies...")

    try:
        with open(requirements_file, 'r') as file:
            logging.info(f"Contents of {requirements_file}:")
            logging.info(file.read())

        logging.info(f"Executing: {pip_executable} install -r {requirements_file}")
        subprocess.check_call([pip_executable, 'install', '-r', requirements_file])

    except subprocess.CalledProcessError as e:
        logging.error("Error occurred while installing dependencies.")
        raise e
    except Exception as e:
        logging.error("An unexpected error occurred:")
        logging.error(str(e))
        raise

    logging.info("Dependencies installed successfully.")




def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

def positive_int(value):
        try:
            ivalue = int(value)
            if ivalue <= 0:
                raise argparse.ArgumentTypeError(f"{value} is an invalid positive int value")
            return ivalue
        except ValueError:
            print("Please specify the total number of alternative scripts to generate: ")
            while True:
                try:
                    return int(input())
                except ValueError:
                    print("Invalid input. Please enter a valid number.")             

def check_latest_version():
    try:
        # Send request to GitHub API to get the latest release version
        response = requests.get('https://api.github.com/repos/yanniedog/autocrew/releases/latest')
        response.raise_for_status()  # Raise an exception for HTTP errors
        latest_release = response.json()
        latest_version = latest_release['tag_name']

        # Compare the latest version from GitHub with the current version
        if version.parse(latest_version) > version.parse(AUTOCREW_VERSION):
            message = f"An updated version of AutoCrew is available: {latest_version}"
            return latest_version, message
        else:
            message = "You are running the latest version of AutoCrew."
            return AUTOCREW_VERSION, message
    except requests.RequestException as e:
        # Handle any request-related errors
        message = f"Error while checking for the latest version (HTTP error): {e}"
        return AUTOCREW_VERSION, message
    except json.JSONDecodeError:
        # Handle JSON decoding errors (if the response is not in JSON format)
        message = "Error while checking for the latest version (Invalid JSON response)."
        return AUTOCREW_VERSION, message
    except Exception as e:
        # Handle any other unforeseen errors
        message = f"Error while checking for the latest version: {e}"
        return AUTOCREW_VERSION, message



def upgrade_autocrew(latest_version):
    backup_dir = '.backup'
    os.makedirs(backup_dir, exist_ok=True)

    # Backup log and config files
    for file_name in ['autocrew.log', 'config.ini']:
        src_path = file_name
        backup_path = os.path.join(backup_dir, f"{file_name}.backup")
        if os.path.exists(src_path):
            shutil.copy(src_path, backup_path)
            logging.info(f"Backing up {src_path} to {backup_path}...")

    update_dir = 'autocrew_update'
    shutil.rmtree(update_dir, ignore_errors=True)

    # Clone the latest version from GitHub
    git_clone_result = subprocess.run(['git', 'clone', 'https://github.com/yanniedog/autocrew.git', update_dir], 
                                      capture_output=True, text=True)

    if git_clone_result.returncode != 0:
        logging.error("Failed to clone the repository:")
        logging.error(git_clone_result.stdout)
        logging.error(git_clone_result.stderr)
        raise RuntimeError("Failed to clone the AutoCrew repository.")

    # File update with confirmation
    for filename in os.listdir(update_dir):
        source_path = os.path.join(update_dir, filename)
        if os.path.isfile(source_path) and filename != 'config.ini':
            confirmation = input(f"Do you want to overwrite {filename}? (yes/no): ").lower()
            if confirmation == 'yes':
                shutil.copyfile(source_path, filename)
                logging.info(f"Copied {filename} to the current directory.")
            else:
                logging.info(f"Skipped updating {filename}.")

    # Update config.ini with previous settings
    update_config_file(update_dir, backup_dir)

    shutil.rmtree(update_dir)
    logging.info("Upgrade process completed.")
    print(f"Upgrade successful. AutoCrew has been updated from version {AUTOCREW_VERSION} to version {latest_version}.")
    sys.exit(0)

def update_config_file(update_dir, backup_dir):
    new_config_path = os.path.join(update_dir, 'config.ini')
    backup_config_path = os.path.join(backup_dir, 'config.ini.backup')
    if os.path.exists(new_config_path) and os.path.exists(backup_config_path):
        config = configparser.ConfigParser()
        config.read(new_config_path)
        config_backup = configparser.ConfigParser()
        config_backup.read(backup_config_path)

        for section in config_backup.sections():
            if not config.has_section(section):
                config.add_section(section)
            for key, value in config_backup.items(section):
                config.set(section, key, value)

        with open('config.ini', 'w') as configfile:
            config.write(configfile)
            logging.info("Updated the config.ini file with previous settings.")
    else:
        logging.error("Missing new or backup config.ini files. Skipping config update.")
def parse_config_parameters(config_params):
    """
    Parse the config parameters provided by the user and return a dictionary.
    """
    config_dict = {}
    for param in config_params:
        try:
            section, key_value = param.split('.', 1)
            key, value = key_value.split('=', 1)
            # Strip whitespace and keep the value as a string
            config_dict.setdefault(section.strip(), {})[key.strip()] = value.strip()
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid config parameter format: {param}")
    return config_dict

def update_config_file_with_params(config_dict, write_to_file=False):
    """
    Update the config.ini file with the parameters provided by the user.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    for section, params in config_dict.items():
        if not config.has_section(section):
            config.add_section(section)
        for key, value in params.items():
            config.set(section, key, str(value))
    if write_to_file:
        with open('config.ini', 'w') as configfile:
            config.write(configfile)
            logging.info("Updated the config.ini file with new settings.")
  

    
def pull_ollama_model(model_name):
    """Pull the specified Ollama model using the ollama pull command."""
    pull_command = ['ollama', 'pull', model_name]
    try:
        subprocess.run(pull_command, check=True, capture_output=False)
        logging.info(f"Successfully pulled Ollama model: {model_name}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to pull Ollama model: {model_name}")
        logging.error(e)
        sys.exit(1)

def truncate_overall_goal(overall_goal, max_length):
    return overall_goal[:max_length]


def handle_install_dependencies(args):
    if args.d:
        install_dependencies()
        sys.exit(0)

def handle_help(args, parser):
    if args.h:
        parser.print_help()
        sys.exit(0)

def handle_upgrade(args, latest_version):
    if args.u:
        if version.parse(latest_version) > version.parse(AUTOCREW_VERSION):
            upgrade_autocrew(latest_version)
        else:
            logging.info("No new version available or you are already running the latest version.")
        sys.exit(0)

def handle_config_update(args):
    if args.c:
        config_dict = parse_config_parameters(args.c)
        update_config_file_with_params(config_dict, write_to_file=args.w)

def generate_and_run_scripts(args, autocrew, truncated_overall_goal):
    csv_file_paths = []  # Initialize csv_file_paths
    num_scripts_to_generate = 1 if not args.m else args.m
    no_script_generation_params = any([args.c, args.h, args.d, args.u])
    if not no_script_generation_params:
        try:
            logging.info(f"Generating {num_scripts_to_generate} alternative scripts...")
            csv_file_paths = autocrew.generate_scripts(truncated_overall_goal, num_scripts_to_generate)

            if args.a:
                for path in csv_file_paths:
                    script_path = path.replace('.csv', '.py')
                    subprocess.run([sys.executable, script_path])
        except Exception as e:
            logging.exception("An error occurred during script generation.")
            sys.exit(1)
    return csv_file_paths

def handle_ranking(args, autocrew, truncated_overall_goal, csv_file_paths):
    if args.r:
        try:
            logging.info("Ranking process initiated.")
            if not csv_file_paths:
                csv_file_paths = autocrew.get_existing_scripts(truncated_overall_goal)

            if not csv_file_paths:
                logging.error("No existing scripts found to rank.")
                sys.exit(1)

            ranked_crews, overall_summary = autocrew.rank_crews(csv_file_paths, args.overall_goal, args.v)
            logging.info(f"Ranking prompt:\n{overall_summary}\n")
            autocrew.save_ranking_output(ranked_crews, truncated_overall_goal)
            logging.info("Ranking process completed.")

        except Exception as e:
            logging.exception("An error occurred during script ranking.")
            sys.exit(1)

def generate_startup_message(latest_version, version_message):
    startup_message = ("\nWelcome to AutoCrew!\n" +
                       "Use the -? or -h command line options to display help information.\n" +
                       "Settings can be modified within \"config.ini\". Scripts are saved in the \"scripts\" subdirectory.\n" +
                       "If you experience any errors, please create an issue on Github and attach \"autocrew.log\":\n" +
                       "https://github.com/yanniedog/autocrew/issues/new\n" +
                       f"\nAutoCrew version: {AUTOCREW_VERSION}\n" +
                       f"{version_message}\n")
    return startup_message


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            'CrewAI Autocrew Script\n\n'
            'Example usages:\n'
            ' python3 autocrew.py -a "Develop a new product" Automatically run scripts after generation\n'
            ' python3 autocrew.py -d Install dependencies from requirements.txt\n'
            ' python3 autocrew.py -h Show this help message and exit\n'
            ' python3 autocrew.py -m5 "Plan a product launch event" Generate scripts for 5 different crews\n'
            ' python3 autocrew.py -r "Evaluate marketing strategies" Rank the generated crews if multiple scripts are created\n'
            ' python3 autocrew.py -u Upgrade to the latest version of AutoCrew\n'
            ' python3 autocrew.py -v "Create a marketing strategy" Provide additional details during execution\n'
            ' python3 autocrew.py -c "BASIC.llm_endpoint=openai" Temporarily use the specified config during execution\n'
            ' python3 autocrew.py -c "BASIC.llm_endpoint=openai" -c "OLLAMA_CONFIG.llm_model=mistral" -w\n'
            ' Write the specified config to the config.ini file\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False
    )

    # Add arguments with capitalized help strings
    parser.add_argument('-a', action='store_true', help='Automatically run the scripts after generation')
    parser.add_argument('-c', action='append', metavar='SECTION.KEY=VALUE', help='Specify Config.ini parameters')
    parser.add_argument('-d', action='store_true', help='Install Dependencies from requirements.txt')
    parser.add_argument('-h', action='store_true', help='Show this Help message and exit')
    parser.add_argument('-m', type=positive_int, help='Generate Multiple alternative scripts')
    parser.add_argument('-r', action='store_true', help='Rank the generated crews if multiple scripts are created')
    parser.add_argument('-u', action='store_true', help='Upgrade to the latest version of AutoCrew')
    parser.add_argument('-v', action='store_true', help='Provide additional details during execution (Verbose mode)')
    parser.add_argument('-w', action='store_true', help='Write specified config to the config.ini file')
    parser.add_argument('overall_goal', nargs='?', type=str, help='The Overall goal for the crew')

    args = parser.parse_args()
    return args, parser

def main():
    setup_logging()
    logging.info("Starting AutoCrew script")
    # clear_screen()  # Commented out to prevent clearing the console screen

    # Global exception handling
    sys.excepthook = handle_exception

    # Check if no command-line parameters are provided
    if len(sys.argv) == 1:
        # No command-line parameters provided, run the interactive setup script
        print("\nWelcome to AutoCrew!\nLet's get started.\n")
        subprocess.run(['python3', 'welcome.py'])
        sys.exit(0)
    
    args, parser = parse_arguments()
    log_command_line_arguments()

    try:
        # Check for the latest version
        latest_version, version_message = check_latest_version()
        startup_message = generate_startup_message(latest_version, version_message)
        logging.info(startup_message)

        # Handle help, install dependencies, and upgrade before proceeding
        handle_help(args, parser)
        handle_install_dependencies(args)
        handle_upgrade(args, latest_version)

        # Update config if specified
        handle_config_update(args)

        autocrew = AutoCrew()
        autocrew.log_config_with_redacted_api_keys()

        if not args.overall_goal:
            args.overall_goal = input("Please set the overall goal for your crew: ")

        # Truncate the overall_goal according to the setting in config.ini
        config = configparser.ConfigParser()
        config.read('config.ini')
        max_length = config.getint('CREWAI_SCRIPTS', 'overall_goal_truncation_for_filenames', fallback=40)
        truncated_overall_goal = truncate_overall_goal(args.overall_goal, max_length)

        # Script Generation and Ranking Process
        csv_file_paths = generate_and_run_scripts(args, autocrew, truncated_overall_goal)
        handle_ranking(args, autocrew, truncated_overall_goal, csv_file_paths)

    except Exception as e:
        logging.exception("An unexpected error occurred: %s", str(e))
        sys.exit(1)
    logging.info("AutoCrew script finished successfully")
    sys.exit(0)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.exception("An unhandled exception occurred: %s", str(e))
        sys.exit(1)
