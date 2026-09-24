def run(args, api):
    for segment in range(4):
        result = yield from api.call("run_vla", {"instruction": args["instruction"], "chunks": 8})
        if result["status"] != "succeeded":
            return {"status": "failed", "data": result["data"], "error_code": result["error_code"]}
    for segment in range(4):
        result = yield from api.call("run_vla", {"instruction": args["instruction"], "chunks": 8})
        if result["status"] != "succeeded":
            return {"status": "failed", "data": result["data"], "error_code": result["error_code"]}
    return {"status": "failed", "error_code": "delegation_budget_exhausted", "data": {"meaning": "Bounded attempt exhausted; no task completion asserted"}}
