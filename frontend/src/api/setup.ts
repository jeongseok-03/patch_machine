import { requestJson } from './http';
import type {
  AccessControlPayload,
  CompanyProfile,
  InitialOfficeSetupResult,
  OfficeBrowseResult,
  OfficeScanReport,
  OfficeScanRequest,
} from './types';

export function browseOfficeFolders(path: string): Promise<OfficeBrowseResult> {
  return requestJson<OfficeBrowseResult>('/api/setup/office/browse', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

export type ReportItem = { text: string; sources: string[] };

export type CompanyReport = {
  progressed?: Array<ReportItem | string>;
  attention?: Array<ReportItem | string>;
  quiet?: Array<ReportItem | string>;
  people?: Array<ReportItem | string>;
  money?: Array<ReportItem | string>;
  read_files?: number;
  changed_files?: number;
  created_at?: string;
};

export function setReportItemStatus(text: string, status: 'done' | 'dismissed'): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>('/api/setup/office/report/item-status', {
    method: 'POST',
    body: JSON.stringify({ text, status }),
  });
}

export function previewScannedDocument(path: string): Promise<{ path: string; filename: string; text: string }> {
  return requestJson<{ path: string; filename: string; text: string }>('/api/setup/office/document-preview', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

export type ReportInterval = 'off' | 'monthly' | 'quarterly' | 'semiannual';

export type CompanyReportStatus = {
  report: CompanyReport;
  schedule: { interval?: ReportInterval };
  is_due: boolean;
};

export function generateCompanyReport(): Promise<CompanyReport> {
  return requestJson<CompanyReport>('/api/setup/office/report/generate', { method: 'POST' });
}

export function fetchCompanyReportStatus(): Promise<CompanyReportStatus> {
  return requestJson<CompanyReportStatus>('/api/setup/office/report/latest');
}

export function saveReportSchedule(interval: ReportInterval): Promise<{ interval?: ReportInterval }> {
  return requestJson<{ interval?: ReportInterval }>('/api/setup/office/report/schedule', {
    method: 'PUT',
    body: JSON.stringify({ interval }),
  });
}

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
