from __future__ import annotations

from backend.agents.registry import (
    AGENT_CONTRACTS,
    AgentKey,
    get_agent_contract,
    get_agent_contract_for_stage,
)
from backend.providers.models.base import ModelCapability


def test_active_agent_registry_is_limited_to_three_agent_flow() -> None:
    assert list(AGENT_CONTRACTS) == [
        AgentKey.ART_DIRECTOR,
        AgentKey.LOGO_DESIGNER,
        AgentKey.IP_DESIGNER,
    ]
    assert [contract.stage for contract in AGENT_CONTRACTS.values()] == [
        "DIRECTIONS",
        "LOGO",
        "IP",
    ]


def test_agent_contracts_lock_stage_capabilities_and_io_contracts() -> None:
    art_director = get_agent_contract(AgentKey.ART_DIRECTOR)
    logo_agent = get_agent_contract(AgentKey.LOGO_DESIGNER)
    ip_designer = get_agent_contract(AgentKey.IP_DESIGNER)

    assert art_director.display_name == "艺术总监 Agent"
    assert art_director.capability is ModelCapability.DIRECTIONS
    assert art_director.input_contract == ["BrandSpec"]
    assert art_director.draft_output_contract == "DirectionDraftOutput"
    assert art_director.final_output_contract == "DirectionOutput"

    assert logo_agent.display_name == "Logo Agent"
    assert logo_agent.capability is ModelCapability.LOGO
    assert logo_agent.input_contract == ["BrandSpec", "Direction"]
    assert logo_agent.draft_output_contract == "LogoDraftOutput"
    assert logo_agent.final_output_contract == "LogoOutput"

    assert ip_designer.display_name == "IP 设计师 Agent"
    assert ip_designer.capability is ModelCapability.IP
    assert ip_designer.input_contract == ["BrandSpec", "LogoConcept"]
    assert ip_designer.draft_output_contract == "IPDraft"
    assert ip_designer.final_output_contract == "IPOutput"


def test_agent_contract_lookup_by_stage() -> None:
    assert get_agent_contract_for_stage("DIRECTIONS").key is AgentKey.ART_DIRECTOR
    assert get_agent_contract_for_stage("LOGO").key is AgentKey.LOGO_DESIGNER
    assert get_agent_contract_for_stage("IP").key is AgentKey.IP_DESIGNER
