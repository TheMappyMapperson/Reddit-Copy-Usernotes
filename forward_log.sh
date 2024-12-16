#!/bin/bash

# define variables. run every hour and upload new log items to discord
# Variables
LOG_FILE="/home/user/log.txt"
WEBHOOK_URL="" # Replace with your actual webhook URL
CURRENT_TIME=$(date +%s)
ONE_HOUR_AGO=$(date -d '1 hour ago' +%s)

# Function to check if a log line is within the last hour
is_within_last_hour() {
    local log_time=$1
    log_epoch=$(date -d "$log_time" +%s 2>/dev/null)
    if [[ $? -eq 0 && $log_epoch -ge $ONE_HOUR_AGO ]]; then
        return 0
    else
        return 1
    fi
}

# Extract lines from the last hour
LINES=$(awk '{if ($1 != "" && $2 != "" && $1 ~ /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/ && $2 ~ /^[0-9]{2}:[0-9]{2}:[0-9]{2}/) print}' "$LOG_FILE" | while read -r line; do
    log_datetime=$(echo "$line" | awk '{print $1 " " $2}' | sed 's/,/./') # Replace comma with dot for seconds parsing
    if is_within_last_hour "$log_datetime"; then
        echo "$line"
    fi
done)

# Prepare JSON payload
if [ -n "$LINES" ]; then
    # Escape double quotes and newline characters, combine all lines into one JSON string
    ESCAPED_LINES=$(echo "$LINES" | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\n/\\n/g')
    
    # Construct JSON payload
    JSON_PAYLOAD="{\"content\": \"$ESCAPED_LINES\"}"

    # Send the extracted lines as JSON to the Discord webhook
    curl -X POST -H "Content-Type: application/json" --data "$JSON_PAYLOAD" "$WEBHOOK_URL"
else
    echo "No new log lines found within the last hour."
fi
