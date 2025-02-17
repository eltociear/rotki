import { assert } from '@/utils/assertions';

export const useRoute = () => {
  const proxy = getCurrentInstance()?.proxy;
  assert(proxy);
  return computed(() => proxy.$route);
};

export const useRouter = () => {
  const proxy = getCurrentInstance()?.proxy;
  assert(proxy);
  return proxy.$router;
};
