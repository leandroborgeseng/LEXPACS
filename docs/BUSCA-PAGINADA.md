# Lista de exames: paginação no servidor e busca sem acento

## De onde vinha o limite de 100/101
Não era o Orthanc nem o proxy: o `LimitFindResults` não está definido no `orthanc.json` do LEXPACS
(padrão 0, sem limite) e o nginx não corta resposta. O corte vinha do OHIF: `useStudyListQuery`
usa `queryLimit ?? 101` e o QIDO sai com `limit=101&offset=0`; a paginação era feita no navegador
sobre esses 101 ("1-50 of 101").

## Como ficou
- O viewer (`lexWorklistApi` em `config/default.js`) chama `POST /clinica-api/worklist/studies`
  com filtros no corpo e `limit`/`offset` da página (50 ou 100). Só a página atual é carregada.
- O portal (`lex-pacs-portal/app/worklist.py`) consulta o Orthanc só para leitura:
  - sem nome: QIDO com `limit`/`offset` + total por `/tools/count-resources` (Orthanc ≥ 1.12.5;
    sem ele, total desconhecido e só "Anterior/Próxima");
  - com nome: `/tools/find` com padrão relaxado e novo filtro no portal (abaixo).
- Nome, prontuário, nº de acesso e descrição não vão para a URL do navegador (ficam na
  sessionStorage da aba, chave `lex.worklist.textFilters`) nem para a URL do gateway (corpo do POST).
  Na URL ficam só período, modalidade, página e tamanho (LP9).

## Busca sem acento: abordagem e limites
O Orthanc 1.12.x compara PatientName sem diferenciar maiúsculas, mas **não ignora acento**, e o
curinga `?` casa um byte (falha em "É", 2 bytes em UTF-8). Conferido em Orthanc local descartável.
Por isso:
1. O portal pega a parte mais longa do nome digitado e troca cada letra que pode ter acento
   (A E I O U C) por `*` (ex.: "jose conceicao" → `*J*S*`). O Orthanc devolve um superconjunto.
2. O portal normaliza o nome gravado (sem acento, maiúsculo, `^` e `,` como espaço) e exige que
   cada parte digitada apareça, em qualquer ordem. Ordena por data (mais recente primeiro) e pagina.

Limites: até 50.000 candidatos por busca (cobre o PACS inteiro, ~35 mil); acima disso o total
fica desconhecido. Nomes muito curtos ou só com vogais/C (ex.: "ana" → `*N*`) trazem muitos
candidatos e ficam mais lentos — o tempo na rede da prefeitura (LP7) ainda precisa ser medido.
Ñ e Ý não são tratados. Sem nome, a ordem "mais recente primeiro" vale dentro da página (LP10).
