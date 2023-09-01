# ccm-python
create cost categories using python

# csv files

these scripts expect csv files. if you are using the excel file format you will need to save it as a csv (comma delimited)

# authentication

the following environment variables should be set:

HARNESS_PLATFORM_API_KEY: a harness api key

HARNESS_ACCOUNT_ID: your harness account identifier

# cost_catagories.py

create cost catagories in harness based on csvs for each cloud

usage: `python3 cost_catagories.py <domain cost center name> <bu cost center name> [csv]`

example: `python3 cost_catagories.py "My Domains" "My BUs" projects.csv`

# get_clusters.py

get all gke clusters in a gcp organization

requires a gcp org id

usage: `GCP_ORG_ID=862299901433 python3 get_clusters.py [Cluster BU CC Name] [project->bu csv file]`
