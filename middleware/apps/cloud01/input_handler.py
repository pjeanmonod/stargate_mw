from pprint import pprint

def format_awx_request(build_request):
    extra_vars = {}
    pprint (build_request)

    job_vars = {
        "region": build_request.get("region"),
        "CorePriCIDR": [str(build_request.get("CorePriCIDR"))],
        "CoreSecCIDR": [str(build_request.get("CoreSecCIDR"))],
        "CorepublicSubnetsPerAZ": int(build_request.get("CorepublicSubnetsPerAZ", 1)),
        "CoreprivateSubnetsPerAZ": int(build_request.get("CoreprivateSubnetsPerAZ", 1)),
        "coreIgw": bool(build_request.get("coreIgw", False)),
        "EdgePriCIDR": [str(build_request.get("EdgePriCIDR"))],
        "EdgeSecCIDR": [str(build_request.get("EdgeSecCIDR"))],
        "EdgepublicSubnetsPerAZ": int(build_request.get("EdgepublicSubnetsPerAZ", 1)),
        "EdgeprivateSubnetsPerAZ": int(build_request.get("EdgeprivateSubnetsPerAZ", 1)),
        "edgeIgw": bool(build_request.get("edgeIgw", False)),
        "azsperVPC": int(build_request.get("azsperVPC", 2)),
        "tags": build_request.get("tags", [])
    }

    extra_vars = {
        "job_vars": [job_vars]
    }

    return extra_vars