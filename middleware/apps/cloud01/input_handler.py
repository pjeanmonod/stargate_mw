from pprint import pprint

def format_awx_request(build_request):
    extra_vars = {}
    pprint (build_request)

    job_vars = {
        'CorePriCIDR': build_request.get('CorePriCIDR'),
        'CoreSecCIDR': build_request.get('CoreSecCIDR'),
        'CoreprivateSubnetsPerAZ': build_request.get('CoreprivateSubnetsPerAZ'),
        'CorepublicSubnetsPerAZ': build_request.get('CorepublicSubnetsPerAZ'),
        'coreIgw': build_request.get('CoreIgw'),
        'EdgePriCIDR': build_request.get('EdgePriCIDR'),
        'EdgeSecCIDR': build_request.get('EdgeSecCIDR'),
        'EdgeprivateSubnetsPerAZ': build_request.get('EdgeprivateSubnetsPerAZ'),
        'EdgepublicSubnetsPerAZ': build_request.get('EdgepublicSubnetsPerAZ'),
        'EdgeIgw' : build_request.get['EdgeIgw'],
        'azsperVPC': build_request.get('azsperVPC'),
        "region": build_request.get("region"),
        "tags": build_request.get("tags"),   
    }

    extra_vars = {
        "job_vars": [job_vars]
    }

    return extra_vars