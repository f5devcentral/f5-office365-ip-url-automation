#**
#** Name   : o365_proxy_bypass_irule
#** Author : brett-at-f5
#** Description: Office365 proxy bypass based on external data-group. Must be applied to an explicit proxy virtual server.
#**
 
when RULE_INIT {
  ## Debug logging control
  # 0 = no logging, 1 = debug logging (Test/Dev Only).
  set static::o365_dbg 0

  ## Data group containing Office 365 URLs that will bypass the forward proxy
  set static::o365_url_dg "o365_url_dg"

  ## SNAT pool settings
  # 0 = use virtual server settings, 1 = enable SNAT pool for O365 traffic
  set static::o365_snat 0
  set static::o365_snat_pool "o365_snat_pool"
}

proc o365_log { log_message } {
  if { $static::o365_dbg } {
    log local0. "timestamp=[clock clicks -milliseconds],vs=[virtual],$log_message"
  }
}

when CLIENT_ACCEPTED {
  call o365_log "[IP::client_addr]:[TCP::client_port] --> [clientside {IP::local_addr}]:[clientside {TCP::local_port}]"
}
 
when HTTP_PROXY_REQUEST {
  call o365_log "[HTTP::method] [HTTP::host] [HTTP::uri] HTTP/[HTTP::version] [HTTP::header User-Agent]"

  # Strip of the port number
  set host [lindex [split [HTTP::host] ":"] 0]
 
  # If the hostname matches a 0ffice 365 domain, enable the forward proxy on the HTTP profile and bypass the explicit proxy pool members.
  if { [class match $host ends_with $static::o365_url_dg] } {
    call o365_log "Data group match. Bypass."
    
    # Use a SNAT pool?
    if { $static::o365_snat } {
      snatpool $static::o365_snat_pool
    }
    
    # Use default route and forward proxy the connection.
    HTTP::proxy enable
  } else {
    # Reverse proxy/load balance the request unmodified to the default explicit proxy pool members.
    HTTP::proxy disable
  }
}

when SERVER_CONNECTED {
  call o365_log "[IP::client_addr]:[TCP::client_port] ([IP::local_addr]:[TCP::local_port]) --> [LB::server addr]:[LB::server port]"
}
