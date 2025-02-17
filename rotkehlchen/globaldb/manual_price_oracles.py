import logging
from typing import Optional

from rotkehlchen.assets.asset import Asset
from rotkehlchen.constants import ZERO
from rotkehlchen.errors.price import NoPriceForGivenTimestamp
from rotkehlchen.globaldb.handler import GlobalDBHandler
from rotkehlchen.history.types import HistoricalPriceOracle
from rotkehlchen.inquirer import Inquirer
from rotkehlchen.interfaces import CurrentPriceOracleInterface
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import Price, Timestamp

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


class ManualPriceOracle:

    def can_query_history(  # pylint: disable=no-self-use
            self,
            from_asset: Asset,  # pylint: disable=unused-argument
            to_asset: Asset,  # pylint: disable=unused-argument
            timestamp: Timestamp,  # pylint: disable=unused-argument
            seconds: Optional[int] = None,  # pylint: disable=unused-argument
    ) -> bool:
        return True

    @classmethod
    def query_historical_price(
        cls,
        from_asset: Asset,
        to_asset: Asset,
        timestamp: Timestamp,
    ) -> Price:
        price_entry = GlobalDBHandler().get_historical_price(
            from_asset=from_asset,
            to_asset=to_asset,
            timestamp=timestamp,
            max_seconds_distance=3600,
            source=HistoricalPriceOracle.MANUAL,
        )
        if price_entry is not None:
            log.debug('Got historical manual price', from_asset=from_asset, to_asset=to_asset, timestamp=timestamp)  # noqa: E501
            return price_entry.price

        raise NoPriceForGivenTimestamp(
            from_asset=from_asset,
            to_asset=to_asset,
            time=timestamp,
        )


class ManualCurrentOracle(CurrentPriceOracleInterface):

    def __init__(self) -> None:
        super().__init__(oracle_name='manual current price oracle')

    def rate_limited_in_last(self, seconds: Optional[int] = None) -> bool:
        return False

    def query_current_price(self, from_asset: Asset, to_asset: Asset) -> Price:
        """
        Searches for a manually specified current price for the `from_asset`. If it finds
        the price, converts it to a price in `to_asset` and returns.
        """
        manual_current_result = GlobalDBHandler().get_manual_current_price(
            asset=from_asset,
        )
        if manual_current_result is None:
            return Price(ZERO)

        current_to_asset, current_price = manual_current_result
        current_to_asset_price = Inquirer().find_price(  # pylint: disable=unexpected-keyword-arg
            from_asset=current_to_asset,
            to_asset=to_asset,
            coming_from_latest_price=True,
        )

        return Price(current_price * current_to_asset_price)
