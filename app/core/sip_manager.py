import logging
from typing import Optional, Mapping, Union, List, Dict
from livekit import api
from livekit.api.sip_service import (
    CreateSIPOutboundTrunkRequest,
    UpdateSIPOutboundTrunkRequest,
    DeleteSIPTrunkRequest,
    ListSIPOutboundTrunkRequest,
    CreateSIPInboundTrunkRequest,
    UpdateSIPInboundTrunkRequest,
    ListSIPInboundTrunkRequest,
    DeleteSIPTrunkRequest,
    CreateSIPDispatchRuleRequest,
    UpdateSIPDispatchRuleRequest,
    ListSIPDispatchRuleRequest,
    DeleteSIPDispatchRuleRequest,
    TransferSIPParticipantRequest,
    CreateSIPParticipantRequest,
    SIPOutboundTrunkInfo,
)

logger = logging.getLogger("sip-manager")

class SIPManager:
    def __init__(self, host: str, api_key: str, api_secret: str):
        self.client = api.LiveKitAPI(host=host, api_key=api_key, api_secret=api_secret)

    # ---------------------- OUTBOUND TRUNKS ----------------------

    async def create_outbound_trunk(
        self,
        name: str,
        address: str,
        numbers: List[str],
        auth_username: str,
        auth_password: str,

    ):
        trunk_info = SIPOutboundTrunkInfo(
            name=name,
            address=address,
            numbers=numbers,
            auth_username=auth_username,
            auth_password=auth_password,
        )
        request = CreateSIPOutboundTrunkRequest(trunk=trunk_info)
        return await self.client.sip.create_sip_outbound_trunk(request)

    async def update_outbound_trunk(self, trunk_id: str, **kwargs):
        request = UpdateSIPOutboundTrunkRequest(sip_trunk_id=trunk_id, **kwargs)
        return await self.client.sip.update_sip_outbound_trunk(request)

    async def delete_trunk(self, trunk_id: str):
        request = DeleteSIPTrunkRequest(sip_trunk_id=trunk_id)
        return await self.client.sip.delete_sip_trunk(request)

    async def list_outbound_trunks(self):
        request = ListSIPOutboundTrunkRequest()
        return await self.client.sip.list_sip_outbound_trunk(request)

    # ---------------------- INBOUND TRUNKS ----------------------

    async def create_inbound_trunk(self, name: str, webhook_url: str, username: Optional[str] = None,
                                   password: Optional[str] = None):
        request = CreateSIPInboundTrunkRequest(
            name=name,
            webhook_url=webhook_url,
            username=username,
            password=password
        )
        return await self.client.sip.create_sip_inbound_trunk(request)

    async def update_inbound_trunk(self, trunk_id: str, **kwargs):
        request = UpdateSIPInboundTrunkRequest(trunk_id=trunk_id, **kwargs)
        return await self.client.sip.update_sip_inbound_trunk(request)

    async def list_inbound_trunks(self):
        request = ListSIPInboundTrunkRequest()
        return await self.client.sip.list_sip_inbound_trunk(request)

    # ---------------------- DISPATCH RULES ----------------------

    async def create_dispatch_rule(self, name: str, trunk_id: str, rule_uri: str):
        #todo
        request = CreateSIPDispatchRuleRequest(
            name=name,
            trunk_id=trunk_id,
            match_request_uri=rule_uri
        )
        return await self.client.sip.create_sip_dispatch_rule(request)

    async def update_dispatch_rule(self, rule_id: str, **kwargs):
        #todo
        request = UpdateSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id, **kwargs)
        return await self.client.sip.update_sip_dispatch_rule(request)

    async def list_dispatch_rules(self):
        request = ListSIPDispatchRuleRequest()
        return await self.client.sip.list_sip_dispatch_rules(request)

    async def delete_dispatch_rule(self, rule_id: str):
        request = DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
        return await self.client.sip.delete_sip_dispatch_rule(request)

    # ---------------------- PARTICIPANT CONTROL ----------------------

    async def create_sip_participant(self, room_name: str, sip_trunk_id: str, sip_call_to: str,
                                     participant_identity: str, wait_until_answered: bool = True,
                                     krisp_enabled: bool = True):
        request = CreateSIPParticipantRequest(
            room_name=room_name,
            sip_trunk_id=sip_trunk_id,
            sip_call_to=sip_call_to,
            participant_identity=participant_identity,
            wait_until_answered=wait_until_answered,
            krisp_enabled= krisp_enabled
        )
        return await self.client.sip.create_sip_participant(request)

    async def transfer_participant(self, participant_identity: str, room_name: str, transfer_to: str):
        request = TransferSIPParticipantRequest(
            participant_identity=participant_identity,
            room_name=room_name,
            transfer_to=transfer_to,

        )
        return await self.client.sip.transfer_sip_participant(request)
