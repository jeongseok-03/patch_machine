import { useEffect, useState } from 'react';

import { browseOfficeFolders, type OfficeBrowseResult } from '../../api';
import Button from '../common/Button';

type Props = {
  onAddRoot: (path: string) => void;
  onAddExclude: (path: string) => void;
  onClose: () => void;
  roots: string[];
  excludes: string[];
};

export default function FolderBrowserModal({ onAddRoot, onAddExclude, onClose, roots, excludes }: Props) {
  const [listing, setListing] = useState<OfficeBrowseResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function open(path: string) {
    setBusy(true);
    setError('');
    try {
      setListing(await browseOfficeFolders(path));
    } catch (err) {
      setError(err instanceof Error ? err.message : '폴더를 열 수 없습니다.');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void open('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const atTop = !listing?.display;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-panel folder-browser">
        <div className="folder-browser-head">
          <strong>폴더 선택</strong>
          <Button variant="secondary" onClick={onClose}>닫기</Button>
        </div>
        <p className="muted">
          폴더를 눌러 안으로 이동하고, [스캔 대상]과 [제외]로 목록에 추가하세요. 여러 개 추가할 수 있습니다.
        </p>
        <div className="folder-browser-path">
          <Button variant="secondary" disabled={atTop || busy} onClick={() => void open(listing?.parent || '')}>
            ← 상위 폴더
          </Button>
          <code>{listing?.display || '내 컴퓨터'}</code>
        </div>
        {listing?.display ? (
          <div className="folder-browser-current">
            <span>현재 폴더를 목록에 추가:</span>
            <Button
              disabled={roots.includes(listing.display)}
              onClick={() => onAddRoot(listing.display)}
            >
              스캔 대상으로 추가
            </Button>
            <Button
              variant="danger"
              disabled={excludes.includes(listing.display)}
              onClick={() => onAddExclude(listing.display)}
            >
              제외 목록에 추가
            </Button>
          </div>
        ) : null}
        {error ? <p className="alert">{error}</p> : null}
        <div className="folder-browser-list">
          {busy ? <p className="muted">불러오는 중...</p> : null}
          {!busy && listing?.entries.length === 0 ? <p className="muted">하위 폴더가 없습니다.</p> : null}
          {!busy && listing
            ? listing.entries.map((entry) => (
                <div className="folder-browser-row" key={entry.path}>
                  <button type="button" className="folder-browser-name" onClick={() => void open(entry.path)}>
                    📁 {entry.name}
                  </button>
                  <div className="folder-browser-row-actions">
                    <Button
                      variant="secondary"
                      disabled={roots.includes(entry.path)}
                      onClick={() => onAddRoot(entry.path)}
                    >
                      스캔 대상
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={excludes.includes(entry.path)}
                      onClick={() => onAddExclude(entry.path)}
                    >
                      제외
                    </Button>
                  </div>
                </div>
              ))
            : null}
        </div>
      </div>
    </div>
  );
}
