import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useImageViewer } from '@ohif/ui-next';
import { Button, Input, Separator } from '@ohif/ui-next';
import { fetchClinicalProfile, type ClinicalPermissions } from '../../../../platform/app/src/routes/WorkList/lexClinicalUser';

const API_BASE = '/clinica-api/reports';

type ReportData = {
  study_instance_uid: string;
  status: string;
  content_html: string;
  author_name: string;
  signed_by: string;
  signed_crm: string;
  signed_at: string | null;
  has_pdf: boolean;
  pdf_filename: string | null;
  visible_to_patient: boolean;
};

function PanelLexReport() {
  const { t, i18n } = useTranslation('LexPacs');
  const { StudyInstanceUIDs } = useImageViewer();
  const studyUid = StudyInstanceUIDs?.[0] || '';
  const editorRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [authorName, setAuthorName] = useState('');
  const [signedBy, setSignedBy] = useState('');
  const [signedCrm, setSignedCrm] = useState('');
  const [status, setStatus] = useState('draft');
  const [hasPdf, setHasPdf] = useState(false);
  const [pdfFilename, setPdfFilename] = useState<string | null>(null);
  const [signedAt, setSignedAt] = useState<string | null>(null);
  const [visibleToPatient, setVisibleToPatient] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [permissions, setPermissions] = useState<ClinicalPermissions | null>(null);

  const isSigned = status === 'signed';
  const canSign = permissions?.can_sign ?? true;
  const canDraft = permissions?.can_draft ?? true;
  const roleLabel = permissions?.role
    ? t(`roles.${permissions.role}`, { defaultValue: permissions.role_label })
    : '';

  const loadReport = useCallback(async () => {
    if (!studyUid) {
      return;
    }
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_BASE}/${encodeURIComponent(studyUid)}`, {
        credentials: 'include',
      });
      const data = (await response.json().catch(() => ({}))) as ReportData & { detail?: string };
      if (!response.ok) {
        throw new Error(data.detail || t('report.errors.load'));
      }
      setStatus(data.status);
      setAuthorName(data.author_name || '');
      setSignedBy(data.signed_by || '');
      setSignedCrm(data.signed_crm || '');
      setSignedAt(data.signed_at);
      setHasPdf(data.has_pdf);
      setPdfFilename(data.pdf_filename);
      setVisibleToPatient(Boolean(data.visible_to_patient));
      if (editorRef.current) {
        editorRef.current.innerHTML = data.content_html || '';
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('report.errors.load'));
    } finally {
      setLoading(false);
    }
  }, [studyUid, t]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  useEffect(() => {
    void fetchClinicalProfile().then(profile => {
      if (profile?.permissions) {
        setPermissions(profile.permissions);
      }
    });
  }, []);

  const execCommand = (command: string) => {
    document.execCommand(command, false);
    editorRef.current?.focus();
  };

  const saveDraft = async () => {
    if (!studyUid || isSigned || !canDraft) {
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const content_html = editorRef.current?.innerHTML || '';
      const response = await fetch(`${API_BASE}/${encodeURIComponent(studyUid)}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content_html, author_name: authorName }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('report.errors.save'));
      }
      setMessage(t('report.draftSaved'));
      setStatus(data.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('report.errors.save'));
    } finally {
      setLoading(false);
    }
  };

  const uploadPdf = async (file: File) => {
    if (!studyUid || isSigned) {
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const form = new FormData();
      form.append('file', file);
      const response = await fetch(`${API_BASE}/${encodeURIComponent(studyUid)}/pdf`, {
        method: 'POST',
        credentials: 'include',
        body: form,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('report.errors.upload'));
      }
      setHasPdf(true);
      setPdfFilename(data.pdf_filename);
      setMessage(t('report.pdfAttached'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('report.errors.upload'));
    } finally {
      setLoading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const signReport = async () => {
    if (!studyUid || isSigned || !canSign) {
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/${encodeURIComponent(studyUid)}/sign`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signed_by: signedBy, signed_crm: signedCrm }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('report.errors.sign'));
      }
      setStatus('signed');
      setSignedAt(data.signed_at);
      setMessage(t('report.signedLocked'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('report.errors.sign'));
    } finally {
      setLoading(false);
    }
  };

  const releaseToPatient = async (release: boolean) => {
    if (!studyUid || !isSigned) {
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const endpoint = release ? 'release' : 'revoke-patient';
      const response = await fetch(`${API_BASE}/${encodeURIComponent(studyUid)}/${endpoint}`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('report.errors.release'));
      }
      setVisibleToPatient(Boolean(data.visible_to_patient));
      setMessage(release ? t('report.released') : t('report.revoked'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('report.errors.release'));
    } finally {
      setLoading(false);
    }
  };

  if (!studyUid) {
    return (
      <div className="text-muted-foreground p-4 text-sm">{t('report.openStudyHint')}</div>
    );
  }

  const signedLine =
    isSigned && signedAt
      ? t('report.signedBy', {
          name: signedBy,
          crm: signedCrm ? t('report.signedByCrm', { crm: signedCrm }) : '',
          date: new Date(signedAt).toLocaleString(i18n.language),
        })
      : null;

  return (
    <div className="text-foreground flex h-full flex-col gap-3 overflow-y-auto p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-primary text-sm font-semibold">{t('report.title')}</h3>
        <div className="flex items-center gap-2">
          {roleLabel ? (
            <span className="text-muted-foreground text-[10px] uppercase tracking-wide">{roleLabel}</span>
          ) : null}
          <span
            className={`rounded px-2 py-0.5 text-xs ${isSigned ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'}`}
          >
            {isSigned ? t('report.signed') : t('report.draft')}
          </span>
        </div>
      </div>

      {signedLine ? <p className="text-muted-foreground text-xs">{signedLine}</p> : null}

      <label className="flex flex-col gap-1 text-xs">
        {t('report.authorLabel')}
        <Input
          value={authorName}
          onChange={e => setAuthorName(e.target.value)}
          disabled={isSigned || loading}
          placeholder={t('report.authorPlaceholder')}
        />
      </label>

      {!isSigned ? (
        <div className="flex flex-wrap gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => execCommand('bold')}
          >
            N
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => execCommand('italic')}
          >
            I
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => execCommand('insertUnorderedList')}
          >
            {t('report.listButton')}
          </Button>
        </div>
      ) : null}

      <div
        ref={editorRef}
        className={`bg-background min-h-[180px] rounded border p-2 text-sm leading-relaxed ${isSigned ? 'opacity-90' : ''}`}
        contentEditable={!isSigned && !loading}
        suppressContentEditableWarning
      />

      <Separator />

      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium">{t('report.pdfSection')}</span>
        {hasPdf ? (
          <a
            className="text-primary text-xs underline"
            href={`${API_BASE}/${encodeURIComponent(studyUid)}/pdf`}
            target="_blank"
            rel="noreferrer"
          >
            {pdfFilename || t('report.openPdf')}
          </a>
        ) : (
          <p className="text-muted-foreground text-xs">{t('report.noPdf')}</p>
        )}
        {!isSigned ? (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              className="text-xs"
              onChange={e => {
                const file = e.target.files?.[0];
                if (file) {
                  uploadPdf(file);
                }
              }}
            />
            <p className="text-muted-foreground text-xs">{t('report.pdfHint')}</p>
          </>
        ) : null}
      </div>

      {!isSigned && canSign ? (
        <>
          <Separator />
          <label className="flex flex-col gap-1 text-xs">
            {t('report.signAsLabel')}
            <Input
              value={signedBy}
              onChange={e => setSignedBy(e.target.value)}
              placeholder={t('report.signAsPlaceholder')}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t('report.crmLabel')}
            <Input
              value={signedCrm}
              onChange={e => setSignedCrm(e.target.value)}
              placeholder={t('report.crmPlaceholder')}
            />
          </label>
        </>
      ) : null}

      {!isSigned && !canSign ? (
        <p className="text-muted-foreground text-xs">{t('report.technicianHint')}</p>
      ) : null}

      {error ? <p className="text-destructive text-xs">{error}</p> : null}
      {message ? <p className="text-primary text-xs">{message}</p> : null}

      {!isSigned ? (
        <div className="mt-auto flex flex-col gap-2 pt-2">
          <Button
            onClick={saveDraft}
            disabled={loading || !canDraft}
          >
            {t('report.saveDraft')}
          </Button>
          {canSign ? (
            <Button
              variant="default"
              className="bg-primary"
              onClick={signReport}
              disabled={loading || !signedBy.trim()}
            >
              {t('report.signReport')}
            </Button>
          ) : null}
        </div>
      ) : canSign ? (
        <div className="mt-auto flex flex-col gap-2 border-t pt-3">
          <span className="text-xs font-medium">{t('report.patientPortal')}</span>
          <p className="text-muted-foreground text-xs">
            {visibleToPatient ? t('report.patientVisible') : t('report.patientHidden')}
          </p>
          {visibleToPatient ? (
            <Button
              variant="ghost"
              onClick={() => releaseToPatient(false)}
              disabled={loading}
            >
              {t('report.removeFromPortal')}
            </Button>
          ) : (
            <Button
              onClick={() => releaseToPatient(true)}
              disabled={loading}
            >
              {t('report.releaseToPatient')}
            </Button>
          )}
        </div>
      ) : isSigned ? (
        <p className="text-muted-foreground mt-auto text-xs">{t('report.signedReleaseHint')}</p>
      ) : null}
    </div>
  );
}

export default PanelLexReport;
