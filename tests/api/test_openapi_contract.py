from fastapi.testclient import TestClient

from apps.api.app.main import app


def get_openapi_spec() -> dict:
    response = TestClient(app).get("/api/openapi.json")

    assert response.status_code == 200
    return response.json()


def schema_ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def json_response_schema(operation: dict, status_code: str) -> dict:
    return operation["responses"][status_code]["content"]["application/json"]["schema"]


def request_body_schema(operation: dict) -> dict:
    return operation["requestBody"]["content"]["application/json"]["schema"]


def assert_path_parameters(operation: dict, expected_names: list[str]) -> None:
    assert [parameter["name"] for parameter in operation["parameters"]] == expected_names
    assert all(parameter["in"] == "path" for parameter in operation["parameters"])
    assert all(parameter["required"] is True for parameter in operation["parameters"])


def test_project_state_and_versions_openapi_contract() -> None:
    spec = get_openapi_spec()

    state_operation = spec["paths"]["/api/v1/projects/{project_id}/state"]["get"]
    assert_path_parameters(state_operation, ["project_id"])
    assert json_response_schema(state_operation, "200") == schema_ref("ProjectStateResponse")
    assert json_response_schema(state_operation, "404") == schema_ref("ErrorDetailResponse")

    versions_operation = spec["paths"]["/api/v1/projects/{project_id}/stages/{stage_key}/versions"][
        "get"
    ]
    assert_path_parameters(versions_operation, ["project_id", "stage_key"])
    versions_schema = json_response_schema(versions_operation, "200")
    assert versions_schema["type"] == "array"
    assert versions_schema["items"] == schema_ref("StageVersionStateResponse")
    assert json_response_schema(versions_operation, "404") == schema_ref("ErrorDetailResponse")


def test_stage_decision_openapi_contract() -> None:
    spec = get_openapi_spec()
    operation = spec["paths"]["/api/v1/projects/{project_id}/stages/{stage_key}/decisions"]["post"]
    decision_schema = spec["components"]["schemas"]["StageDecisionRequest"]

    assert_path_parameters(operation, ["project_id", "stage_key"])
    assert request_body_schema(operation) == schema_ref("StageDecisionRequest")
    assert json_response_schema(operation, "202") == schema_ref("StageDecisionResponse")
    assert json_response_schema(operation, "404") == schema_ref("ErrorDetailResponse")
    assert json_response_schema(operation, "409") == schema_ref("ErrorDetailResponse")
    assert decision_schema["additionalProperties"] is False
    assert decision_schema["required"] == ["version_id"]
    assert decision_schema["properties"]["version_id"]["format"] == "uuid"
    assert decision_schema["properties"]["selected_item_id"]["anyOf"][0]["minLength"] == 1
    assert decision_schema["properties"]["selected_item_id"]["anyOf"][0]["maxLength"] == 120
    assert decision_schema["properties"]["confirmed"]["anyOf"][0]["const"] is True
    assert decision_schema["properties"]["action"]["enum"] == [
        "SELECT_VERSION",
        "CONFIRM_VERSION",
    ]
    assert decision_schema["properties"]["action"]["default"] == "SELECT_VERSION"


def test_proposal_export_manifest_openapi_contract() -> None:
    spec = get_openapi_spec()
    manifest_operation = spec["paths"]["/api/v1/projects/{project_id}/exports/proposal-manifest"][
        "get"
    ]
    markdown_operation = spec["paths"]["/api/v1/projects/{project_id}/exports/proposal.md"]["get"]
    zip_operation = spec["paths"]["/api/v1/projects/{project_id}/exports/proposal.zip"]["get"]
    manifest_schema = spec["components"]["schemas"]["ProposalExportManifestResponse"]

    assert_path_parameters(manifest_operation, ["project_id"])
    assert json_response_schema(manifest_operation, "200") == schema_ref(
        "ProposalExportManifestResponse"
    )
    assert json_response_schema(manifest_operation, "404") == schema_ref("ErrorDetailResponse")
    assert json_response_schema(manifest_operation, "409") == schema_ref("ErrorDetailResponse")
    assert manifest_schema["required"] == [
        "project_id",
        "project_name",
        "proposal_version_id",
        "proposal_stage_run_id",
        "decision_id",
        "title",
        "narrative",
        "sections",
        "asset_refs",
        "generated_at",
    ]

    assert_path_parameters(markdown_operation, ["project_id"])
    markdown_content = markdown_operation["responses"]["200"]["content"]
    assert markdown_content["text/markdown"]["schema"] == {"type": "string"}
    assert json_response_schema(markdown_operation, "404") == schema_ref("ErrorDetailResponse")
    assert json_response_schema(markdown_operation, "409") == schema_ref("ErrorDetailResponse")

    assert_path_parameters(zip_operation, ["project_id"])
    zip_content = zip_operation["responses"]["200"]["content"]
    assert zip_content["application/zip"]["schema"] == {"type": "string", "format": "binary"}
    assert json_response_schema(zip_operation, "404") == schema_ref("ErrorDetailResponse")
    assert json_response_schema(zip_operation, "409") == schema_ref("ErrorDetailResponse")


def test_stage_control_openapi_contract() -> None:
    spec = get_openapi_spec()
    control_schema = spec["components"]["schemas"]["StageControlRequest"]

    for action in ("redo", "skip", "generate"):
        operation = spec["paths"][f"/api/v1/projects/{{project_id}}/stages/{{stage_key}}/{action}"][
            "post"
        ]
        body_schema = request_body_schema(operation)

        assert_path_parameters(operation, ["project_id", "stage_key"])
        assert body_schema["anyOf"] == [schema_ref("StageControlRequest"), {"type": "null"}]
        assert json_response_schema(operation, "202") == schema_ref("StageControlResponse")
        assert json_response_schema(operation, "404") == schema_ref("ErrorDetailResponse")
        assert json_response_schema(operation, "409") == schema_ref("ErrorDetailResponse")

    assert control_schema["additionalProperties"] is False
    assert "required" not in control_schema
    assert control_schema["properties"]["source_version_id"]["anyOf"][0]["format"] == "uuid"
    assert control_schema["properties"]["reason"]["anyOf"][0]["maxLength"] == 500
