# Lista de exames: paginação no servidor e busca sem acento

## De onde vinha o limite de 100/101
Não era o Orthanc nem o proxy: o `LimitFindResults` não está definido no `orthanc.json` do LEXPACS
(padrão 0, sem limite) e o nginx não corta resposta. O corte vinha do OHIF: `useStudyListQuery`
usa `queryLimit ?? 101` e o QIDO sai com `limit=101&offset=0`; a paginação era feita no navegador
sobre esses 101 ("1-50 of 101").

## Como ficou (índice do portal)
- O viewer chama `POST /clinica-api/worklist/studies` com filtros no corpo e `limit`/`offset`.
- O portal mantém um índice SQLite próprio (`app/worklist_index.py`, arquivo
  `worklist_index.db` ao lado do `users.db`, ou `WORKLIST_INDEX_PATH`): UID e ID Orthanc do
  estudo, data/hora, nome normalizado (sem acento, minúsculo), modalidades, ID do paciente,
  nº de acesso e descrição normalizada. Sem pixel e sem o nome original. Migração só aditiva.
- Sincronização só por GET no Orthanc: carga inicial por QIDO paginado (3.000 estudos em ~1 s
  no box) e depois incremental pelo `/changes` (NewStudy/StableStudy entram, Deleted sai), com
  checkpoint em `worklist_meta.changes_seq`. A carga inicial (e a reconstrução) roda numa thread
  em segundo plano no startup, sob um lock único: buscas simultâneas nunca disparam duas
  sincronizações. A busca não espera a carga: enquanto ela roda, a API devolve
  `index: {status, indexed, total}` e `partial: true`, e a lista mostra "Preparando a busca no
  acervo… X de N exames indexados" (resultados parciais), consultando de novo a cada 3 s. Depois
  da carga, o incremental roda antes da busca só se o lock estiver livre (não bloqueia).
- O arquivo do índice nasce com permissão 0600 e fica no volume `lex-data` do portal, que o
  gateway nginx não monta; nenhuma rota do gateway o serve (teste de integração).
- Busca, total e ordem "mais recente primeiro" valem para o resultado todo (SQL no índice).
  O Orthanc só recebe um QIDO com os UIDs da página.
- Nome: cada parte digitada (≥3 letras) precisa aparecer no nome, em qualquer ordem, sem
  acento: "jose conceicao" acha CONCEIÇÃO^JOSÉ e vice-versa. Não há mais curinga relaxado
  (`*N*`). Menos de 3 letras: nome exato.
- Nome, prontuário, nº de acesso e descrição não vão para a URL do navegador (sessionStorage
  `lex.worklist.textFilters`) nem para a URL do gateway (corpo do POST). Logs: só contagem e tempo.

## Tempos (box, 3.000 estudos sintéticos ZZTESTE, via gateway, 3 medições)
Carga inicial do índice: 0,9 s (log do portal).

| Caso | Total | Tempo (s) |
|---|---|---|
| nome "ana" | 300 | 0,037 / 0,036 / 0,038 |
| nome "jose" | 301 | 0,037 / 0,037 / 0,036 |
| nome "maria" | 301 | 0,042 / 0,041 / 0,037 |
| primeira página | 3.000 | 0,036 / 0,038 / 0,040 |
| última página (offset 2.950) | 3.000 | 0,036 / 0,038 / 0,036 |

## Limites
- Um estudo novo aparece na próxima busca (o incremental roda antes dela). Mudança de tags sem
  evento de estudo no `/changes` só entra numa recarga (apagar o arquivo do índice).
- Se o `/changes` do Orthanc for podado antes do checkpoint, é preciso recarregar o índice.
- O tempo na rede da prefeitura com ~35 mil estudos (LP7) ainda precisa ser medido.

## Falha na carga, "Tentar de novo" e rebuild

- Se a carga inicial falhar (Orthanc indisponível), o índice fica em `status: "error"` e a resposta
  vem com `partial: false`: a tela mostra "Busca no acervo indisponível no momento. Tente novamente
  em alguns minutos." e **não** re-consulta a cada 3 s.
- Intervalo mínimo entre tentativas de carga: `WORKLIST_INDEX_RETRY_SECONDS` (padrão 60). O botão
  "Tentar de novo" fica desabilitado com contagem ("Tentar de novo em N s"); o backend aplica o mesmo
  intervalo em `POST /api/worklist/index/retry` (429 + `Retry-After` antes do prazo). Exige sessão clínica.
- `rebuild` apaga as linhas do índice numa transação antes de recarregar: estudo removido do Orthanc
  não reaparece.
- A sincronização síncrona antiga virou `_sync_now_for_tests()` (só testes); nenhuma rota a chama
  (há teste garantindo).
