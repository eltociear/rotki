from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from rotkehlchen.accounting.structures import (
    Balance,
    HistoryBaseEntry,
    HistoryEventSubType,
    HistoryEventType,
)
from rotkehlchen.chain.ethereum.decoding.interfaces import DecoderInterface
from rotkehlchen.chain.ethereum.decoding.structures import ActionItem
from rotkehlchen.chain.ethereum.structures import EthereumTxReceiptLog
from rotkehlchen.chain.ethereum.typing import string_to_ethereum_address
from rotkehlchen.chain.ethereum.utils import asset_normalized_value, ethaddress_to_asset
from rotkehlchen.typing import ChecksumEthAddress, EthereumTransaction, Location
from rotkehlchen.user_messages import MessagesAggregator
from rotkehlchen.utils.misc import hex_or_bytes_to_address, hex_or_bytes_to_int

if TYPE_CHECKING:
    from rotkehlchen.chain.ethereum.decoding.base import BaseDecoderTools
    from rotkehlchen.chain.ethereum.manager import EthereumManager

HISTORY = b'\x89M\xbf\x12b\x19\x9c$\xe1u\x02\x98\xa3\x84\xc7\t\x16\x0fI\xd1cB,\xc6\xce\xe6\x94\xc77\x13\xf1\xd2'  # noqa: E501
SWAPPED = b'\xe2\xce\xe3\xf6\x83`Y\x82\x0bg9C\x85:\xfe\xbd\x9b0&\x12]\xab\rwB\x84\xe6\xf2\x8aHU\xbe'  # noqa: E501


class Oneinchv1Decoder(DecoderInterface):
    def __init__(
            self,
            ethereum_manager: 'EthereumManager',
            base_tools: 'BaseDecoderTools',
            msg_aggregator: MessagesAggregator,
    ) -> None:
        self.ethereum_manager = ethereum_manager
        self.base = base_tools
        self.msg_aggregator = msg_aggregator

    def _decode_history(
            self,
            tx_log: EthereumTxReceiptLog,
            transaction: EthereumTransaction,  # pylint: disable=unused-argument
            decoded_events: List[HistoryBaseEntry],  # pylint: disable=unused-argument
            all_logs: List[EthereumTxReceiptLog],  # pylint: disable=unused-argument
    ) -> Tuple[Optional[HistoryBaseEntry], Optional[ActionItem]]:
        sender = hex_or_bytes_to_address(tx_log.topics[1])
        if not self.base.is_tracked(sender):
            return None, None

        from_token_address = hex_or_bytes_to_address(tx_log.data[0:32])
        to_token_address = hex_or_bytes_to_address(tx_log.data[32:64])
        from_asset = ethaddress_to_asset(from_token_address)
        to_asset = ethaddress_to_asset(to_token_address)
        if None in (from_asset, to_asset):
            return None, None

        from_raw = hex_or_bytes_to_int(tx_log.data[64:96])
        from_amount = asset_normalized_value(from_raw, from_asset)  # type: ignore
        to_raw = hex_or_bytes_to_int(tx_log.data[96:128])
        to_amount = asset_normalized_value(to_raw, to_asset)  # type: ignore

        for event in decoded_events:
            if event.event_type == HistoryEventType.SPEND and event.location_label == sender and from_amount == event.balance.amount and from_asset == event.asset:  # noqa: E501
                # find the send event
                event.event_type = HistoryEventType.TRADE
                event.event_subtype = HistoryEventSubType.SPEND
                event.counterparty = '1inch-v1'
                event.notes = f'Swap {from_amount} {from_asset.symbol} in 1inch-v1 from {event.location_label}'  # noqa: E501
            elif event.event_type == HistoryEventType.RECEIVE and event.location_label == sender and to_amount == event.balance.amount and to_asset == event.asset:  # noqa: E501
                # find the receive event
                event.event_type = HistoryEventType.TRADE
                event.event_subtype = HistoryEventSubType.RECEIVE
                event.counterparty = '1inch-v1'
                event.notes = f'Receive {to_amount} {to_asset.symbol} from 1inch-v1 swap in {event.location_label}'  # noqa: E501
                # use this index as the event may be an ETH transfer and appear at the start
                event.sequence_index = tx_log.log_index

        return None, None

    def _decode_swapped(  # pylint: disable=no-self-use
            self,
            tx_log: EthereumTxReceiptLog,
            transaction: EthereumTransaction,
            decoded_events: List[HistoryBaseEntry],  # pylint: disable=unused-argument
            all_logs: List[EthereumTxReceiptLog],  # pylint: disable=unused-argument
    ) -> Tuple[Optional[HistoryBaseEntry], Optional[ActionItem]]:
        """We use the Swapped event to get the fee kept by 1inch"""
        to_token_address = hex_or_bytes_to_address(tx_log.topics[2])
        to_asset = ethaddress_to_asset(to_token_address)
        if to_asset is None:
            return None, None

        to_raw = hex_or_bytes_to_int(tx_log.data[32:64])
        fee_raw = hex_or_bytes_to_int(tx_log.data[96:128])
        if fee_raw == 0:
            return None, None  # no need to do anything for zero fee taken

        full_amount = asset_normalized_value(to_raw + fee_raw, to_asset)
        sender_address = None
        for event in decoded_events:
            # Edit the full amount in the swap's receive event
            if event.event_type == HistoryEventType.TRADE and event.event_subtype == HistoryEventSubType.RECEIVE and event.counterparty == '1inch-v1':  # noqa: E501
                event.balance.amount = full_amount
                event.notes = f'Receive {full_amount} {event.asset.symbol} from 1inch-v1 swap in {event.location_label}'  # noqa: E501
                sender_address = event.location_label
                break

        if sender_address is None:
            return None, None

        # And now create a new event for the fee
        fee_amount = asset_normalized_value(fee_raw, to_asset)
        fee_event = HistoryBaseEntry(
            event_identifier='0x' + transaction.tx_hash.hex(),
            sequence_index=tx_log.log_index,
            timestamp=transaction.timestamp,
            location=Location.BLOCKCHAIN,
            location_label=sender_address,
            asset=to_asset,
            balance=Balance(amount=fee_amount),
            notes=f'Deduct {fee_amount} {to_asset.symbol} from {sender_address} as 1inch-v1 fees',
            event_type=HistoryEventType.SPEND,
            event_subtype=HistoryEventSubType.FEE,
            counterparty='1inch-v1',
        )
        return fee_event, None

    def decode_action(
            self,
            tx_log: EthereumTxReceiptLog,
            transaction: EthereumTransaction,
            decoded_events: List[HistoryBaseEntry],  # pylint: disable=unused-argument
            all_logs: List[EthereumTxReceiptLog],  # pylint: disable=unused-argument
            action_items: Optional[List[ActionItem]],  # pylint: disable=unused-argument
    ) -> Tuple[Optional[HistoryBaseEntry], Optional[ActionItem]]:
        if tx_log.topics[0] == HISTORY:
            return self._decode_history(tx_log=tx_log, transaction=transaction, decoded_events=decoded_events, all_logs=all_logs)  # noqa: E501
        if tx_log.topics[0] == SWAPPED:
            return self._decode_swapped(tx_log=tx_log, transaction=transaction, decoded_events=decoded_events, all_logs=all_logs)  # noqa: E501

        return None, None

    def addresses_to_decoders(self) -> Dict[ChecksumEthAddress, Tuple[Any, ...]]:
        return {
            string_to_ethereum_address('0x11111254369792b2Ca5d084aB5eEA397cA8fa48B'): (self.decode_action,),  # noqa: E501
        }
