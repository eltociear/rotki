import { Blockchain } from '@rotki/common/lib/blockchain';
import { MaybeRef } from '@vueuse/core';
import { Routes } from '@/router/routes';
import { api } from '@/services/rotkehlchen-api';
import { useAssetInfoRetrieval } from '@/store/assets/retrieval';
import { TradeLocationData, tradeLocations } from '@/types/trades';
import { assert } from '@/utils/assertions';

export const setupLocationInfo = () => {
  const isSupportedBlockchain = (identifier: string): boolean => {
    return Object.values(Blockchain).includes(identifier as any);
  };

  const { assetName } = useAssetInfoRetrieval();

  const getLocation = (identifier: MaybeRef<string>): TradeLocationData => {
    const id = get(identifier);
    if (isSupportedBlockchain(id)) {
      return {
        name: get(assetName(id)),
        identifier: id,
        exchange: false,
        imageIcon: true,
        icon: api.assets.assetImageUrl(id),
        detailPath: `${Routes.ACCOUNTS_BALANCES_BLOCKCHAIN.route}#blockchain-balances-${id}`
      };
    }

    const locationFound = tradeLocations.find(
      location => location.identifier === id
    );
    assert(!!locationFound, 'location should not be falsy');
    return locationFound;
  };

  return {
    getLocation
  };
};
