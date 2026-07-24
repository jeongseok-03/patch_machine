// Barrel for the API client. Splitting api.ts by domain keeps modules small;
// existing `from '../api'` imports resolve here unchanged.
export * from './types';
export * from './auth';
export * from './setup';
export * from './uploads';
export * from './documents';
export * from './integrations';
export * from './llm';
export * from './work';
export * from './agent';
export * from './admin';
export * from './memory';
