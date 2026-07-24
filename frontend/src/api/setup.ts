import { requestJson } from './http';
import type {
  AccessControlPayload,
  CompanyProfile,
  InitialOfficeSetupResult,
  OfficeScanReport,
  OfficeScanRequest,
} from './types';

export function previewOfficeScan(payload: OfficeScanRequest): Promise<OfficeScanReport> {
  return requestJson<OfficeScanReport>('/api/setup/office/scan-preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function analyzeInitialOfficeSetup(payload: {
  message: string;
  upload_ids: string[];
  intent?: string;
  company_profile?: CompanyProfile;
  scan?: OfficeScanRequest | null;
}): Promise<InitialOfficeSetupResult> {
  return requestJson<InitialOfficeSetupResult>('/api/setup/office/analyze', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function applyInitialOfficeSetup(payload: InitialOfficeSetupResult): Promise<{ ok: boolean; access_control: AccessControlPayload }> {
  return requestJson<{ ok: boolean; access_control: AccessControlPayload }>('/api/setup/office/apply', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
