from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from backend.agents.schemas.common import ContractModel
from backend.providers.models.base import ModelCapability


class AgentKey(StrEnum):
    ART_DIRECTOR = "art_director"
    LOGO_DESIGNER = "logo_designer"
    IP_DESIGNER = "ip_designer"


class AgentContract(ContractModel):
    key: AgentKey
    display_name: str = Field(min_length=1, max_length=80)
    stage: str = Field(min_length=1, max_length=40)
    capability: ModelCapability
    prompt_version: str = Field(min_length=1, max_length=100)
    input_contract: list[str] = Field(min_length=1, max_length=10)
    draft_output_contract: str = Field(min_length=1, max_length=120)
    final_output_contract: str = Field(min_length=1, max_length=120)


AGENT_CONTRACTS: dict[AgentKey, AgentContract] = {
    AgentKey.ART_DIRECTOR: AgentContract(
        key=AgentKey.ART_DIRECTOR,
        display_name="艺术总监 Agent",
        stage="DIRECTIONS",
        capability=ModelCapability.DIRECTIONS,
        prompt_version="directions-v1",
        input_contract=["BrandSpec"],
        draft_output_contract="DirectionDraftOutput",
        final_output_contract="DirectionOutput",
    ),
    AgentKey.LOGO_DESIGNER: AgentContract(
        key=AgentKey.LOGO_DESIGNER,
        display_name="Logo Agent",
        stage="LOGO",
        capability=ModelCapability.LOGO,
        prompt_version="logo-v1",
        input_contract=["BrandSpec", "Direction"],
        draft_output_contract="LogoDraftOutput",
        final_output_contract="LogoOutput",
    ),
    AgentKey.IP_DESIGNER: AgentContract(
        key=AgentKey.IP_DESIGNER,
        display_name="IP 设计师 Agent",
        stage="IP",
        capability=ModelCapability.IP,
        prompt_version="ip-v1",
        input_contract=["BrandSpec", "LogoConcept"],
        draft_output_contract="IPDraft",
        final_output_contract="IPOutput",
    ),
}


def get_agent_contract(key: AgentKey) -> AgentContract:
    return AGENT_CONTRACTS[key]


def get_agent_contract_for_stage(stage: str) -> AgentContract:
    for contract in AGENT_CONTRACTS.values():
        if contract.stage == stage:
            return contract
    raise KeyError(f"No active agent contract for stage {stage}")
