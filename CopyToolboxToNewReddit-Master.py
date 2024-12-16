import argparse 
import os
import praw
import prawcore
import time
import json
import base64
import zlib
import csv
from datetime import datetime, timedelta, timezone
import pandas as pd
import logging

# Define full paths to the required files
base_path = "/home/ubuntu/usernotes_backup/meta"
log_file_path = os.path.join(base_path, "log.txt")
notes_file_path = os.path.join(base_path, "notes.txt")
csv_file_path = os.path.join(base_path, "notes.csv")

# Setup logging to use the full path for the log file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# BEGIN TIME CALCULATION
start_time = time.time()

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument("subreddits_list", help="Comma-separated list of subreddit names")
parser.add_argument("credentials", help="Choose which credentials to use: 'ufos-credentials' or 'UFOs_Sightings-credentials'")
parser.add_argument("twoFA", nargs="?", default=None, help="Optional two-factor authentication code")
args = parser.parse_args()

subreddits_list = args.subreddits_list.split(',')
credentials_choice = args.credentials

# Store credentials directly in the script
credentials = {
    'sub1-credentials': {
        'client_id': '',
        'client_secret': '',
        'password': '',
        'username': '',
        'user_agent': 'script:UFOs_Sightings-bot:v2.0.0 (by /u/SaltyAdminBot)'
    },
    'sub2-credentials': {
        'client_id': '',
        'client_secret': '',
        'password': '',
        'username': '',
        'user_agent': 'script:UFOs_Sightings-bot:v2.0.0 (by /u/SaltyAdminBot)'
    }
}

if credentials_choice not in credentials:
    logger.error(f"Error: Credentials '{credentials_choice}' not found, exiting...")
    exit(1)

selected_credentials = credentials[credentials_choice]

def login():
    # Connect to Reddit API using the embedded credentials
    reddit = praw.Reddit(
        client_id=selected_credentials['client_id'],
        client_secret=selected_credentials['client_secret'],
        username=selected_credentials['username'],
        password=selected_credentials['password'],
        user_agent=selected_credentials['user_agent']
    )
    
    # Modify the password if the twoFA is provided
    if args.twoFA:
        modified_password = "{}:{}{}".format(selected_credentials['password'], args.twoFA, '')
        reddit = praw.Reddit(
            client_id=selected_credentials['client_id'],
            client_secret=selected_credentials['client_secret'],
            username=selected_credentials['username'],
            password=modified_password,
            user_agent=selected_credentials['user_agent']
        )
    return reddit

def save_usernotes(reddit):
    for subreddit_name in subreddits_list:
        try:
            subreddit = reddit.subreddit(subreddit_name)
            usernotes_page = subreddit.wiki['usernotes']  # Fetch usernotes page

            # Save the content of the usernotes page to the full path of notes.txt
            with open(notes_file_path, 'w', encoding='utf-8') as notes_file:
                notes_file.write(usernotes_page.content_md)

            logger.info(f'Saved json wiki data from /r/{subreddit_name} to {notes_file_path}')

        except prawcore.exceptions.Forbidden:
            logger.error(f"Error: /r/{subreddit_name}/wiki/usernotes (HTTP 403: Forbidden)")
        except prawcore.exceptions.TooManyRequests:
            logger.error(f"Error: /r/{subreddit_name}/wiki/usernotes (HTTP 429: Too Many Requests)")
            logger.error(f"LIMIT: Per minute rate limit exceeded, exiting...\n")
            exit(1)
        except Exception as error:
            logger.error(f"Error: {error}")

def decompress_notes(notes_blob):
    try:
        notes_blob_decoded = base64.b64decode(notes_blob)
        decompressed_notes = zlib.decompress(notes_blob_decoded).decode()
        return json.loads(decompressed_notes)
    except Exception as e:
        logger.error("Failed to decompress notes:", e)
        return None

def read_toolbox_notes(file_path):
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except Exception as e:
        logger.error("Failed to read Toolbox notes from file:", e)
        return None

def convert_timestamp_to_datetime(timestamp):
    try:
        # Convert Unix timestamp to a human-readable date/time format using timezone-aware datetime
        return datetime.fromtimestamp(timestamp, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.error(f"Failed to convert timestamp {timestamp}: {e}")
        return None

# Function to save notes to CSV
def save_notes_to_csv(file_path, notes):
    try:
        with open(file_path, mode='w', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            # Add the header with 'Username', 'Note Text', and 'Time'
            writer.writerow(['Username', 'Note Text', 'Time'])
            for username, usernotes in notes.items():
                for note in usernotes['ns']:
                    # Convert the timestamp to a human-readable format
                    time_str = convert_timestamp_to_datetime(note['t'])
                    writer.writerow([username, note['n'], time_str])
        logger.info(f"JSON converted to CSV with date and time saved to {file_path}")
    except Exception as e:
        logger.error("Failed to save notes to CSV:", e)

# Filter rows not within the last 1 hour
def filter_csv_by_time(csv_file_path):
    try:
        # Load the CSV file into a DataFrame
        df = pd.read_csv(csv_file_path)

        # Convert 'Time' column to timezone-aware datetime
        df['Time'] = pd.to_datetime(df['Time'], errors='coerce', utc=True)

        # Get the current UTC time as a timezone-aware datetime
        current_time = pd.Timestamp.now(tz='UTC')

        # Filter rows from the past 24 hours
        filtered_df = df[df['Time'] >= (current_time - pd.Timedelta(hours=1))]

        # Save the filtered DataFrame back to the CSV file
        filtered_df.to_csv(csv_file_path, index=False)
        logger.info(f"Filtered rows within last hour saved to {csv_file_path}")
    except Exception as e:
        logger.error(f"Failed to filter CSV by time: {e}")

# Function to add mod notes
def add_mod_note(reddit, subreddit_name, username, text):
    try:
        # Truncate the text to 249 characters if it exceeds 250 characters
        if len(text) > 250:
            text = text[:249]
        
        subreddit = reddit.subreddit(subreddit_name)
        subreddit.mod.notes.create(label="ABUSE_WARNING", note=text, redditor=username)
        logger.info(f"Adding note for {username}:{text}")
    except Exception as e:
        logger.error(f"Error adding mod note for {username}: {str(e)}")
        # If an error occurs, move on to the next username
        return

# Run it
reddit = login()

logger.info(f"Scanning subreddits: {subreddits_list}\n")
save_usernotes(reddit)

# Decompress and process notes
# Read Toolbox notes from file
toolbox_notes = read_toolbox_notes(notes_file_path)

# Decompress notes if present
if toolbox_notes:
    notes_blob = toolbox_notes.get('blob')
    if notes_blob:
        decompressed_notes = decompress_notes(notes_blob)
        if decompressed_notes:
            # Save notes to CSV using the full path for notes.csv
            save_notes_to_csv(csv_file_path, decompressed_notes)
            # Filter CSV file by time
            filter_csv_by_time(csv_file_path)
        else:
            logger.info("No decompressed notes found.")
    else:
        logger.info("No notes blob found.")
else:
    logger.info("No Toolbox notes found in the file.")

# Add mod notes from CSV
# Initialize variables for rate limiting
requests_count = 0
start_time = time.time()

# Read CSV file and add mod notes
with open(csv_file_path, 'r', newline='', encoding='utf-8') as csvfile:
    reader = csv.reader(csvfile)
    next(reader)  # Skip the first row (header)
    for row in reader:
        # Check if the rate limit has been reached
        if requests_count >= 1000:
            # Calculate time remaining until the 10-minute window resets
            elapsed_time = time.time() - start_time
            if elapsed_time < 600:
                remaining_time = 600 - elapsed_time
                logger.info(f"Waiting for {remaining_time} seconds to respect rate limit...")
                time.sleep(remaining_time)
                # Reset variables after waiting
                requests_count = 0
                start_time = time.time()
        
        username = row[0]  # Assuming the username is in the first column
        text = row[1]  # User Note is in second column
        for subreddit_name in subreddits_list:
            add_mod_note(reddit, subreddit_name, username, text)
        logger.info(f"Copied note for {username}")
        # Increment the request count
        requests_count += 1
        time.sleep(2)

# Calculate and print runtime summary
end_time = time.time()
elapsed_time = end_time - start_time
rounded_elapsed_time = int(elapsed_time) + (elapsed_time > int(elapsed_time))
std_hours = rounded_elapsed_time // 3600
std_minutes = (rounded_elapsed_time % 3600) // 60
std_seconds = rounded_elapsed_time % 60

logger.info(f"\nSUMMARY:\n")
logger.info(f"             Runtime : {rounded_elapsed_time} seconds ({std_hours:02}:{std_minutes:02}:{std_seconds:02})")
