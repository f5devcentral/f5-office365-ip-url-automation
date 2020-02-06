#!/bin/python
# -*- coding: utf-8 -*-
# Office 365 IP Address and URL Web Service Automation for BIG-IP
# https://docs.microsoft.com/en-us/Office365/Enterprise/office-365-ip-web-service
# Version: 1.06
# Last Modified: 4th December 2019
# Original author: Makoto Omura, F5 Networks Japan G.K.
#
# v1.05: Updated for SSL Orchestrator by Kevin Stewart, SSA, F5 Networks
# v1.06: Updated by Brett Smith, Principal Systems Engineer
# v1.06: Ability to create data groups and/or URL categories. IPv4/IPv6 data group support only.
#
# This Sample Software provided by the author is for illustrative
# purposes only which provides customers with programming information
# regarding the products. This software is supplied "AS IS" without any
# warranties and support.
#
# The author assumes no responsibility or liability for the use of the
# software, conveys no license or title under any patent, copyright, or
# mask work right to the product.
#
# The author reserves the right to make changes in the software without
# notification. The author also make no representation or warranty that
# such application will be suitable for the specified use without
# further testing or modification.

import httplib
import urllib
import uuid
import os
import re
import json
import commands
import datetime
import sys

#-----------------------------------------------------------------------
# User Options - Configure as desired
#-----------------------------------------------------------------------

# O365 Record types to download & update
use_url = 0     # Create custom category for URL based proxy bypassing - requires APM: 0=do not use, 1=use
use_url_dg = 1  # Create data group for URL based proxy bypassing: 0=do not use, 1=use
use_ipv4 = 1    # Create data group for IPv4 based routing: 0=do not use, 1=use
use_ipv6 = 0    # Create data group for IPv6 based routing: 0=do not use, 1=use

# O365 "SeviceArea" (application) to consume
care_common = 1     # "Common": 0=do not care, 1=care
care_exchange = 1   # "Exchange": 0=do not care, 1=care
care_skype = 1      # "Skype": 0=do not care, 1=care
care_sharepoint = 1 # "SharePoint": 0=do not care, 1=care
care_yammer = 1     # "Yammer": 0=do not care, 1=care

# Action if O365 endpoint list is not updated
force_o365_record_refresh = 0   # 0=do not update, 1=update (for test/debug purpose)

# BIG-IP HA Configuration
device_group_name = "device-group1"     # Name of Sync-Failover Device Group.  Required for HA paired BIG-IP.
ha_config = 0                           # 0=stand alone, 1=HA paired

# Log configuration
log_level = 1   # 0=none, 1=normal, 2=verbose

# Microsoft Web Service URIs (enable only one webservice version)
uri_ms_o365_endpoints = "/endpoints/Worldwide?ClientRequestId="
#uri_ms_o365_endpoints = "/endpoints/USGovDoD?ClientRequestId="
#uri_ms_o365_endpoints = "/endpoints/USGovGCCHigh?ClientRequestId="
#uri_ms_o365_endpoints = "/endpoints/China?ClientRequestId="
#uri_ms_o365_endpoints = "/endpoints/Germany?ClientRequestId="


#-----------------------------------------------------------------------
# System Options - Modify only when necessary
#-----------------------------------------------------------------------

# O365 custom URL category
o365_categories = "Office365"

# BIG-IP Data Group names
urls_dg = "o365_url_dg"
ipv4_dg = "o365_ipv4_dg"
ipv6_dg = "o365_ipv6_dg"

# Work directory, file name for guid & version management
work_directory = "/var/tmp/o365"
file_name_guid = "/var/tmp/o365/guid.txt"
file_ms_o365_version = "/var/tmp/o365/o365_version.txt"
log_dest_file = "/var/log/o365_update"
dg_file_name_urls = "/var/tmp/o365/o365_urls.txt"
dg_file_name_ip4 = "/var/tmp/o365/o365_ip4.txt"
dg_file_name_ip6 = "/var/tmp/o365/o365_ip6.txt"

# Microsoft Web Service URLs
url_ms_o365_endpoints = "endpoints.office.com"
url_ms_o365_version = "endpoints.office.com"
uri_ms_o365_version = "/version?ClientRequestId="


#-----------------------------------------------------------------------
# Implementation - Please do not modify
#-----------------------------------------------------------------------
list_urls_to_bypass = []
list_urls_to_bypass_fin = []
string_urls_to_bypass_fin = ""
list_ips4_to_pbr = []
list_ips6_to_pbr = []
failover_state = ""

def log(lev, msg):
    if log_level >= lev:
        log_string = "{0:%Y-%m-%d %H:%M:%S}".format(datetime.datetime.now()) + " " + msg + "\n"
        f = open(log_dest_file, "a")
        f.write(log_string)
        f.flush()
        f.close()
    return

def main():

    # -----------------------------------------------------------------------
    # Check if this BIG-IP is ACTIVE for the traffic group (= traffic_group_name)
    # -----------------------------------------------------------------------
    result = commands.getoutput("tmsh show /cm failover-status field-fmt")

    if ("status ACTIVE" in result)\
        or (ha_config == 0):
        failover_state = "active"       # For future use
        log(1, "This BIG-IP is ACTIVE. Initiating O365 update.")
    else:
        failover_state = "non-active"   # For future use
        log(1, "This BIG-IP is STANDBY. Aborting O365 update.")
        sys.exit(0)


    # -----------------------------------------------------------------------
    # GUID management
    # -----------------------------------------------------------------------
    # Create guid file if not existent
    if not os.path.isdir(work_directory):
        os.mkdir(work_directory)
        log(1, "Created work directory " + work_directory + " because it did not exist.")
    if not os.path.exists(file_name_guid):
        f = open(file_name_guid, "w")
        f.write("\n")
        f.flush()
        f.close()
        log(1, "Created GUID file " + file_name_guid + " because it did not exist.")

    # Read guid from file and validate.  Create one if not existent
    f = open(file_name_guid, "r")
    f_content = f.readline()
    f.close()
    if re.match('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', f_content):
        guid = f_content
        log(2, "Valid GUID is read from local file " + file_name_guid + ".")
    else:
        guid = str(uuid.uuid4())
        f = open(file_name_guid, "w")
        f.write(guid)
        f.flush()
        f.close()
        log(1, "Generated a new GUID, and saved it to " + file_name_guid + ".")


    # -----------------------------------------------------------------------
    # O365 endpoints list version check
    # -----------------------------------------------------------------------
    # Read version of previously received record
    if os.path.isfile(file_ms_o365_version):
        f = open(file_ms_o365_version, "r")
        f_content = f.readline()
        f.close()
        # Check if the VERSION record format is valid
        if re.match('[0-9]{10}', f_content):
            ms_o365_version_previous = f_content
            log(2, "Valid previous VERSION found in " + file_ms_o365_version + ".")
        else:
            ms_o365_version_previous = "1970010200"
            f = open(file_ms_o365_version, "w")
            f.write(ms_o365_version_previous)
            f.flush()
            f.close()
            log(1, "Valid previous VERSION was not found.  Wrote dummy value in " + file_ms_o365_version + ".")
    else:
        ms_o365_version_previous = "1970010200"
        f = open(file_ms_o365_version, "w")
        f.write(ms_o365_version_previous)
        f.flush()
        f.close()
        log(1, "Valid previous VERSION was not found.  Wrote dummy value in " + file_ms_o365_version + ".")


    # -----------------------------------------------------------------------
    # O365 endpoints list VERSION check
    # -----------------------------------------------------------------------
    request_string = uri_ms_o365_version + guid
    conn = httplib.HTTPSConnection(url_ms_o365_version)
    conn.request('GET', request_string)
    res = conn.getresponse()

    if not res.status == 200:
        # MS O365 version request failed
        log(1, "VERSION request to MS web service failed.  Assuming VERSIONs did not match, and proceed.")
        dict_o365_version = {}
    else:
        # MS O365 version request succeeded
        log(2, "VERSION request to MS web service was successful.")
        dict_o365_version = json.loads(res.read())

    ms_o365_version_latest = ""
    for record in dict_o365_version:
        if record.has_key('instance'):
            if record["instance"] == "Worldwide" and record.has_key("latest"):
                latest = record["latest"]
                if re.match('[0-9]{10}', latest):
                    ms_o365_version_latest = latest
                    f = open(file_ms_o365_version, "w")
                    f.write(ms_o365_version_latest)
                    f.flush()
                    f.close()

    log(2, "Previous VERSION is " + ms_o365_version_previous)
    log(2, "Latest VERSION is " + ms_o365_version_latest)

    if ms_o365_version_latest == ms_o365_version_previous and force_o365_record_refresh == 0:
        log(1, "You already have the latest MS O365 URL/IP Address list: " + ms_o365_version_latest + ". Aborting operation.")
        sys.exit(0)


    # -----------------------------------------------------------------------
    # Request O365 endpoints list & put it in dictionary
    # -----------------------------------------------------------------------
    request_string = uri_ms_o365_endpoints + guid
    conn = httplib.HTTPSConnection(url_ms_o365_endpoints)
    conn.request('GET', request_string)
    res = conn.getresponse()

    if not res.status == 200:
        log(1, "ENDPOINTS request to MS web service failed. Aborting operation.")
        sys.exit(0)
    else:
        log(2, "ENDPOINTS request to MS web service was successful.")
        dict_o365_all = json.loads(res.read())

    # Process for each record(id) of the endpoint JSON data
    for dict_o365_record in dict_o365_all:
        service_area = str(dict_o365_record['serviceArea'])
        id = str(dict_o365_record['id'])

        if (care_common and service_area == "Common") \
            or (care_exchange and service_area == "Exchange") \
            or (care_sharepoint and service_area == "SharePoint") \
            or (care_skype and service_area == "Skype") \
            or (care_yammer and service_area == "Yammer"):

            if use_url or use_url_dg:
                # Append "urls" if existent in each record
                if dict_o365_record.has_key('urls'):
                    list_urls = list(dict_o365_record['urls'])
                    for url in list_urls:
                        list_urls_to_bypass.append(url)

                # Append "allowUrls" if existent in each record
                if dict_o365_record.has_key('allowUrls'):
                    list_allow_urls = list(dict_o365_record['allowUrls'])
                    for url in list_allow_urls:
                        list_urls_to_bypass.append(url)

                # Append "defaultUrls" if existent in each record
                if dict_o365_record.has_key('defaultUrls'):
                    list_default_urls = dict_o365_record['defaultUrls']
                    for url in list_default_urls:
                        list_urls_to_bypass.append(url)

            if use_ipv4 or use_ipv6:
                # Append "ips" if existent in each record
                if dict_o365_record.has_key('ips'):
                    list_ips = list(dict_o365_record['ips'])
                    for ip in list_ips:
                        if re.match('^.+:', ip):
                            list_ips6_to_pbr.append(ip)
                        else:
                            list_ips4_to_pbr.append(ip)

    num_list_urls_to_bypass = len(list_urls_to_bypass)
    num_list_ips4_to_pbr = len(list_ips4_to_pbr)
    num_list_ips6_to_pbr = len(list_ips6_to_pbr)
    log(1, "Number of ENDPOINTS to import : URL:" + str(num_list_urls_to_bypass) + ", IPv4 host/net:" + str(num_list_ips4_to_pbr) + ", IPv6 host/net:" + str(num_list_ips6_to_pbr))


    # -----------------------------------------------------------------------
    # O365 endpoint URLs re-formatted to fit into custom URL category
    # -----------------------------------------------------------------------
    if use_url:
        # Initialize the url string
        str_urls_to_bypass = ""

        # Create new or clean out existing URL category - add the latest version as first entry
        result = commands.getoutput("tmsh list sys url-db url-category " + o365_categories)
        if "was not found" in result:
            result2 = commands.getoutput("tmsh create /sys url-db url-category " + o365_categories + " display-name " + o365_categories)
            result3 = commands.getoutput("tmsh modify /sys url-db url-category " + o365_categories + " urls replace-all-with { https://" + ms_o365_version_latest + " { type exact-match } }")
            log(2, "O365 custom URL category not found. Created new O365 custom category: " + o365_categories)
        else:
            result2 = commands.getoutput("tmsh modify /sys url-db url-category " + o365_categories + " urls replace-all-with { https://" + ms_o365_version_latest + "/ { type exact-match } }")
            log(2, "O365 custom URL caegory exists. Clearing entries for new data: " + o365_categories) 
    
        # Remove duplicate URLs in the list
        urls_undup = list(set(list_urls_to_bypass))
    
        # Loop through URLs and insert into URL category    
        for url in urls_undup:
            # Force URL to lower case
            url = url.lower()

            # If URL starts with an asterisk, set as a glob-match URL, otherwise exact-match. Send to a string.
            if url.startswith('*'):
                log(2, "Creating glob-match entries for: " + url)
                # Escaping any asterisk characters
                url_processed = re.sub('\*', '\\*', url)
                # Both HTTPS and HTTP category lookups use "https://", with the subtle difference that the HTTP URLs match an entry with no trailing forward slash"
                str_urls_to_bypass = str_urls_to_bypass + " urls add { \"https://" + url_processed + "/\" { type glob-match } } urls add { \"https://" + url_processed + "\" { type glob-match } }"
            else:
                log(2, "Creating exact-match entries for: " + url)
                # Both HTTPS and HTTP category lookups use "https://", with the subtle difference that the HTTP URLs match an entry with no trailing forward slash"
                str_urls_to_bypass = str_urls_to_bypass + " urls add { https://" + url + "/ { type exact-match } } urls add { https://" + url + " { type exact-match } }"

        # Import the URL entries
        result = commands.getoutput("tmsh modify /sys url-db url-category " + o365_categories + str_urls_to_bypass)

    # -----------------------------------------------------------------------
    # O365 endpoints URL asterisk removal and re-format to fit into Data Group
    # -----------------------------------------------------------------------
    if use_url_dg:
        # Process asterisk nicely.  Force lower case letter.
        for url in list_urls_to_bypass:
            url_processed = re.sub('^.*[*][^.]*', '', url).lower()
            list_urls_to_bypass_fin.append(url_processed)

        # URL sort & dedupe. Generate file for External Data Group
        fout = open(dg_file_name_urls, 'w')
        for url in (list(sorted(set(list_urls_to_bypass_fin)))):
            fout.write(str(url) + " := 1,\n")
        fout.flush()
        fout.close()

        #-----------------------------------------------------------------------
        # Data Group File update
        #-----------------------------------------------------------------------
        # The object appears in WebUI: System › File Management : Data Group File List >> xxx_object
        # Name of the Data Group is given in urls_dg
        # Name of the Data Group File is urls_dg + "_object"

        result = commands.getoutput("tmsh list sys file data-group " + urls_dg + "_object")
        # Create or update Data Group File from text file (given for variable "dg_file_name_urls")
        if "was not found" in result:
            result2 = commands.getoutput("tmsh create /sys file data-group " + urls_dg + "_object type string source-path file:" + dg_file_name_urls)
            log(2, "Data Group File " + urls_dg + "_object was not found.  Created from " + dg_file_name_urls + ".")
        else:
            result2 = commands.getoutput("tmsh modify /sys file data-group " + urls_dg + "_object source-path file:" + dg_file_name_urls)
            log(2, "Data Group File " + urls_dg + "_object was found.  Updated from " + dg_file_name_urls + ".")

        #-----------------------------------------------------------------------
        # Make sure Data Group exists that corresponds to File update
        #-----------------------------------------------------------------------
        # The object appears in WebUI: Local Traffic >> iRules : Data Group List >> (External File) xxx
        # The object needs to exist, but does not have to be explicitly updated by this script

        result = commands.getoutput("tmsh list /ltm data-group external " + urls_dg)
        if "was not found" in result:
            result2 = commands.getoutput("tmsh create /ltm data-group external " + urls_dg + " external-file-name " + urls_dg + "_object")
            log(2, "Data Group " + urls_dg + " was not found.  Creating it from " + urls_dg + "_object")

    # -----------------------------------------------------------------------
    # IPv4 addresses saved into text files separately
    # -----------------------------------------------------------------------
    # Process IP dictionaries
    if use_ipv4:
        # Write IPv4 list
        fout = open(dg_file_name_ip4, 'w')
        for ip4 in (list(sorted(set(list_ips4_to_pbr)))):
            fout.write("network " + str(ip4) + ",\n")
        fout.flush()
        fout.close()

        #-----------------------------------------------------------------------
        # Data Group File update
        #-----------------------------------------------------------------------
        # The object appears in WebUI: System › File Management : Data Group File List >> xxx_object
        # Name of the Data Group is given in ipv4_dg
        # Name of the Data Group File is ipv4_dg + "_object"

        result = commands.getoutput("tmsh list sys file data-group " + ipv4_dg + "_object")
        # Create or update Data Group File from text file (given for variable "dg_file_name_ip4")
        if "was not found" in result:
            result2 = commands.getoutput("tmsh create /sys file data-group " + ipv4_dg + "_object type ip source-path file:" + dg_file_name_ip4)
            log(2, "Data Group File " + ipv4_dg + "_object was not found.  Created from " + dg_file_name_ip4 + ".")
        else:
            result2 = commands.getoutput("tmsh modify /sys file data-group " + ipv4_dg + "_object source-path file:" + dg_file_name_ip4)
            log(2, "Data Group File " + ipv4_dg + "_object was found.  Updated from " + dg_file_name_ip4 + ".")

        #-----------------------------------------------------------------------
        # Make sure Data Group exists that corresponds to File update
        #-----------------------------------------------------------------------
        # The object appears in WebUI: Local Traffic >> iRules : Data Group List >> (External File) xxx
        # The object needs to exist, but does not have to be explicitly updated by this script

        result = commands.getoutput("tmsh list /ltm data-group external " + ipv4_dg)
        if "was not found" in result:
            result2 = commands.getoutput("tmsh create /ltm data-group external " + ipv4_dg + " external-file-name " + ipv4_dg + "_object")
            log(2, "Data Group " + ipv4_dg + " was not found.  Creating it from " + ipv4_dg + "_object")

    # -----------------------------------------------------------------------
    # IPv6 addresses saved into text files separately
    # -----------------------------------------------------------------------
    # Process IP dictionaries
    if use_ipv6:
        # Write IPv6 list
        fout = open(dg_file_name_ip6, 'w')
        for ip6 in (list(sorted(set(list_ips6_to_pbr)))):
            fout.write("network " + str(ip6) + ",\n")
        fout.flush()
        fout.close()

        #-----------------------------------------------------------------------
        # Data Group File update
        #-----------------------------------------------------------------------
        # The object appears in WebUI: System › File Management : Data Group File List >> xxx_object
        # Name of the Data Group is given in ipv6_dg
        # Name of the Data Group File is ipv6_dg + "_object"

        result = commands.getoutput("tmsh list sys file data-group " + ipv6_dg + "_object")
        # Create or update Data Group File from text file (given for variable "dg_file_name_ip6")
        if "was not found" in result:
            result2 = commands.getoutput("tmsh create /sys file data-group " + ipv6_dg + "_object type ip source-path file:" + dg_file_name_ip6)
            log(2, "Data Group File " + ipv6_dg + "_object was not found.  Created from " + dg_file_name_ip6 + ".")
        else:
            result2 = commands.getoutput("tmsh modify /sys file data-group " + ipv6_dg + "_object source-path file:" + dg_file_name_ip6)
            log(2, "Data Group File " + ipv6_dg + "_object was found.  Updated from " + dg_file_name_ip6 + ".")

        #-----------------------------------------------------------------------
        # Make sure Data Group exists that corresponds to File update
        #-----------------------------------------------------------------------
        # The object appears in WebUI: Local Traffic >> iRules : Data Group List >> (External File) xxx
        # The object needs to exist, but does not have to be explicitly updated by this script

        result = commands.getoutput("tmsh list /ltm data-group external " + ipv6_dg)
        if "was not found" in result:
            result2 = commands.getoutput("tmsh create /ltm data-group external " + ipv6_dg + " external-file-name " + ipv6_dg + "_object")
            log(2, "Data Group " + ipv6_dg + " was not found.  Creating it from " + ipv6_dg + "_object")

    #-----------------------------------------------------------------------
    # Save config
    #-----------------------------------------------------------------------
    log(1, "Saving BIG-IP Configuration.")
    result = commands.getoutput("tmsh save /sys config")
    log(2, result + "\n")


    #-----------------------------------------------------------------------
    # Initiate Config Sync: Device to Group
    #-----------------------------------------------------------------------
    if ha_config == 1:
        log(1, "Initiating Config-Sync.")
        result = commands.getoutput("tmsh run cm config-sync to-group " + device_group_name)
        log(2, result + "\n")

    log(1, "Completed O365 URL/IP address update process.")


if __name__=='__main__':
    main()
