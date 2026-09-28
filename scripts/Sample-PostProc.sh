#!/bin/sh
# Example of a post processing script for SABnzbd
# All information is passed via SAB_* environment variables

echo
echo Started as $0
echo
echo "Result directory =" "$SAB_COMPLETE_DIR"
echo "NZB name         =" "$SAB_FILENAME"
echo "Job name         =" "$SAB_FINAL_NAME"
echo "Category         =" "$SAB_CAT"
echo "Group            =" "$SAB_GROUP"
echo "Status           =" "$SAB_PP_STATUS"
echo "Failure URL      =" "$SAB_FAILURE_URL"
