import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useImageViewer } from '@ohif/ui-next';
import { Button, Input, Separator } from '@ohif/ui-next';

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

  const isSigned = status === 'signed';

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
        throw new Error(data.detail || 'Não foi possível carregar o laudo.');
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
      setError(err instanceof Error ? err.message : 'Erro ao carregar laudo.');
    } finally {
      setLoading(false);
    }
  }, [studyUid]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const execCommand = (command: string) => {
    document.execCommand(command, false);
    editorRef.current?.focus();
  };

  const saveDraft = async () => {
    if (!studyUid || isSigned) {
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
        throw new Error(data.detail || 'Não foi possível salvar o rascunho.');
      }
      setMessage('Rascunho salvo.');
      setStatus(data.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar.');
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
        throw new Error(data.detail || 'Não foi possível anexar o PDF.');
      }
      setHasPdf(true);
      setPdfFilename(data.pdf_filename);
      setMessage('PDF anexado ao exame.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro no upload.');
    } finally {
      setLoading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const signReport = async () => {
    if (!studyUid || isSigned) {
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
        throw new Error(data.detail || 'Não foi possível assinar o laudo.');
      }
      setStatus('signed');
      setSignedAt(data.signed_at);
      setMessage('Laudo assinado e bloqueado para edição.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao assinar.');
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
        throw new Error(data.detail || 'Não foi possível atualizar a liberação.');
      }
      setVisibleToPatient(Boolean(data.visible_to_patient));
      setMessage(
        release
          ? 'Laudo liberado no portal do paciente.'
          : 'Laudo removido do portal do paciente.'
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao liberar laudo.');
    } finally {
      setLoading(false);
    }
  };

  if (!studyUid) {
    return (
      <div className="text-muted-foreground p-4 text-sm">Abra um exame para editar o laudo.</div>
    );
  }

  return (
    <div className="text-foreground flex h-full flex-col gap-3 overflow-y-auto p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-primary text-sm font-semibold">Laudo</h3>
        <span
          className={`rounded px-2 py-0.5 text-xs ${isSigned ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'}`}
        >
          {isSigned ? 'Assinado' : 'Rascunho'}
        </span>
      </div>

      {isSigned && signedAt ? (
        <p className="text-muted-foreground text-xs">
          Assinado por {signedBy}
          {signedCrm ? ` — CRM ${signedCrm}` : ''} em {new Date(signedAt).toLocaleString('pt-BR')}
        </p>
      ) : null}

      <label className="flex flex-col gap-1 text-xs">
        Autor do laudo
        <Input
          value={authorName}
          onChange={e => setAuthorName(e.target.value)}
          disabled={isSigned || loading}
          placeholder="Nome do radiologista"
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
            • Lista
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
        <span className="text-xs font-medium">PDF do laudo</span>
        {hasPdf ? (
          <a
            className="text-primary text-xs underline"
            href={`${API_BASE}/${encodeURIComponent(studyUid)}/pdf`}
            target="_blank"
            rel="noreferrer"
          >
            {pdfFilename || 'Abrir PDF anexado'}
          </a>
        ) : (
          <p className="text-muted-foreground text-xs">Nenhum PDF anexado.</p>
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
            <p className="text-muted-foreground text-xs">
              Ou redija o laudo acima — pode usar texto, PDF ou ambos antes de assinar.
            </p>
          </>
        ) : null}
      </div>

      {!isSigned ? (
        <>
          <Separator />
          <label className="flex flex-col gap-1 text-xs">
            Assinar como
            <Input
              value={signedBy}
              onChange={e => setSignedBy(e.target.value)}
              placeholder="Nome para assinatura"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            CRM (opcional)
            <Input
              value={signedCrm}
              onChange={e => setSignedCrm(e.target.value)}
              placeholder="Ex.: 12345-SP"
            />
          </label>
        </>
      ) : null}

      {error ? <p className="text-destructive text-xs">{error}</p> : null}
      {message ? <p className="text-primary text-xs">{message}</p> : null}

      {!isSigned ? (
        <div className="mt-auto flex flex-col gap-2 pt-2">
          <Button
            onClick={saveDraft}
            disabled={loading}
          >
            Salvar rascunho
          </Button>
          <Button
            variant="default"
            className="bg-primary"
            onClick={signReport}
            disabled={loading || !signedBy.trim()}
          >
            Assinar laudo
          </Button>
        </div>
      ) : (
        <div className="mt-auto flex flex-col gap-2 border-t pt-3">
          <span className="text-xs font-medium">Portal do paciente</span>
          <p className="text-muted-foreground text-xs">
            {visibleToPatient
              ? 'O paciente pode ver este laudo no portal.'
              : 'O laudo ainda não está visível para o paciente.'}
          </p>
          {visibleToPatient ? (
            <Button
              variant="ghost"
              onClick={() => releaseToPatient(false)}
              disabled={loading}
            >
              Remover do portal
            </Button>
          ) : (
            <Button
              onClick={() => releaseToPatient(true)}
              disabled={loading}
            >
              Liberar laudo ao paciente
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export default PanelLexReport;
