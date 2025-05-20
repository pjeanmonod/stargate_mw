from pprint import pprint

def format_awx_request(build_request):
    extra_vars = {}
    pprint (build_request)

    job_vars = {
        "vpcName": build_request.get("vpcName"),
        "ipv4CIDR": build_request.get("ipv4CIDR"),
        "region": build_request.get("region"),
        "tags": build_request.get("tags"),   
    }

    extra_vars = {
        "job_vars": [job_vars]
    }

    return extra_vars