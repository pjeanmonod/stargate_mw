from pprint import pprint

def format_awx_request(build_request):
    extra_vars = {}
    preprod_clients = ['anb', 'xoc', 'xpc', 'xqc']
    job_data = build_request.get("job_data")
    
    if job_data.get('client_code').lower() in preprod_clients:
        set_leak_client_nets = "no"
    else:
        set_leak_client_nets = "yes"
    
    master_ticket = build_request.get("master_ticket")
    nsx_pri_site = job_data.get("nsx_pri_site")
    master_cluster = job_data.get("master_cluster") if len(job_data["master_cluster"]) > 0 else "no"

    pri_region_mapping = {
        "prdc": "eu",
        "fr2": "eu",
        "nye": "na",
        "fpc": "na",
        "tra": "na",
        "jse": "eu",
        "hk2": "as",
    }
    country_code_mappping = {
        "prdc": "uk",
        "fr2": "de",
        "nye": "us",
        "fpc": "us",
        "tra": "ca",
        "jse": "sa",
        "hk2": "hk"
    }

    job_vars = {
        "added_nets": [], # legacy var but still neds to be provided
        "added_nets_out": [], # legacy var but still neds to be provided
        "primary_var_prefix": job_data.get("client_code"),
        "client_domain": job_data.get("client_domain"),
        "nsx_pri_site": nsx_pri_site,
        "nsx_sec_site": job_data.get("nsx_sec_site"),
        "country_code": country_code_mappping.get(nsx_pri_site),
        "primary_region": pri_region_mapping.get(nsx_pri_site),
        "clientman_net": [job_data.get("client_man_network")],
        "nagios_mgmt_nets": job_data.get("monitored_nets", []),
        "clientdc_net": job_data.get("client_DC_nets"),
        "leak_client_nets": set_leak_client_nets, # default not to be chosen by user
        "master_cluster": master_cluster,
        "vms": job_data.get("vms"),
        "build_azure": job_data.get("build_azure")       
    }

    extra_vars = {
        "master_ticket": master_ticket,
        "job_vars": job_vars
    }

    return extra_vars