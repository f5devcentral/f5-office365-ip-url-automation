# Office 365 IP and URL Web Service Automation for BIG-IP

## Synopsis

This Python script will perform REST API calls to the Office 365 IP Address and URL web service (https://docs.microsoft.com/en-us/Office365/Enterprise/office-365-ip-web-service) and create Data-Groups and/or Custom URL Category.

Up to three Data-Groups are created, based on the configurable options. A Data-Group can be created for:
- IPv4 Addresses
- IPv6 Addresses
- URL/FQDN

The Custom URL Category requires APM or SSLO to be licensed. This category can be referenced within the APM/SWG Per-Request Policy and SSLO Security Policy (or iRule).

Examples of each Data-Group and Custom URL Category is below.

## Installation

Copy the Python script `o365_ip_url_automation.py` to `/shared/scripts/` directory on the BIG-IP. Create the `/shared/scripts/` directory if it does not exist.

Update the permissions so the script is executable. `chmod u+x o365_ip_url_automation.py`

Edit the script and change the configurable options to suit your setup. Note: `ha_config = 1` option will cause a configuration sync to the device group in a Device Service Cluster (DSC). This may not be desirable, use with caution.


## Usage

Run the script for the first time and verify it's working correctly by monitoring the log file `/var/log/o365_update`. You may need to change the log level.

Add a cron entry to run once a day or as desired.

`0 3 * * * /bin/python /shared/scripts/o365_ip_url_automation.py >/dev/null 2>&1`

## Screenshots
### External Data-group with URLs:
 
![o365_url_dg](https://github.com/brett-at-f5/f5-office365-ip-url-automation/blob/master/o365_url_dg.png)
 
### External Data-group with IPv4 CIDR:
 
![o365_ipv4_dg](https://github.com/brett-at-f5/f5-office365-ip-url-automation/blob/master/o365_ipv4_dg.png)
 
### External Data-group with IPv6 CIDR:
 
![o365_ipv6_dg](https://github.com/brett-at-f5/f5-office365-ip-url-automation/blob/master/o365_ipv6_dg.png)
 
### URL Custom Category (APM or SSLO license required):
 
![o365_url_category](https://github.com/brett-at-f5/f5-office365-ip-url-automation/blob/master/o365_url_category.png)


## Contributors
### Original Author: Makoto Omura, F5 Networks Japan
### Updated for SSL Orchestrator by Kevin Stewart, SSA, F5 Networks
### Updated by Brett Smith, Principal Systems Engineer, F5 Networks Australia
