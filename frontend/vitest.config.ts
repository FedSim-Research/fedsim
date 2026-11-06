import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Let jsdom provide storage instead of Node's file-backed Web Storage.
    execArgv: ['--no-experimental-webstorage'],
  },
});
