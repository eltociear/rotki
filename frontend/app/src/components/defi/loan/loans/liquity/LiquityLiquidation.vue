<template>
  <stat-card :title="tc('loan_liquidation.title')">
    <loan-row medium :title="tc('loan_collateral.liquidation_price')">
      <amount-display
        show-currency="ticker"
        fiat-currency="USD"
        :value="price"
        :min-width="18"
      />
    </loan-row>
  </stat-card>
</template>

<script setup lang="ts">
import { BigNumber } from '@rotki/common';
import LoanRow from '@/components/defi/loan/LoanRow.vue';
import StatCard from '@/components/display/StatCard.vue';

defineProps({
  price: {
    required: true,
    type: BigNumber
  },
  asset: {
    required: true,
    type: String
  }
});

const { tc } = useI18n();
</script>
