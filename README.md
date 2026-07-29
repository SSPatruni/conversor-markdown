# Conversor Markdown

Converte documentos para Markdown por uma janela simples, sem linha de comando. Foi feito para quem lida com autos processuais extensos em PDF e quer o texto em `.md` para ler, buscar e trabalhar.

Tudo roda na sua máquina. Nenhum arquivo é enviado para servidor.

## Por que existe

Os conversores online funcionam, mas têm três problemas para quem trabalha com processo judicial.

O arquivo sai da sua máquina. Autos com dados de partes e terceiros não deveriam trafegar por serviço de terceiro.

A saída vem suja. Nos testes que motivaram este projeto, um conversor online inseriu 352 cabeçalhos `##` falsos em um único agravo, preservou o espaçamento de texto justificado em 3.012 trechos, o que quebra a busca por expressão exata, e colou colunas de tabela, com resultados como `PartesAdvogados` e `8513424202/06/2026`.

O rodapé do PJe se repete em toda página. Aquele bloco com "Este documento foi gerado pelo usuário", "Assinado eletronicamente por" e "Num. X - Pág. Y" ocupou entre 18% e 26% dos arquivos medidos.

Este programa resolve os três.

## Recursos

- Seleção múltipla de arquivos por janela do Windows, com barra de progresso e status por arquivo
- Extração de PDF pelo PDFium, o mesmo motor do Chrome
- Remoção opcional do rodapé repetido do PJe
- Normalização de espaços de justificação, que restaura a busca por expressão exata
- Normalização de ligaduras tipográficas, de modo que `Certiﬁco` vira `Certifico` e passa a ser encontrado com Ctrl+F
- Modo alternativo com detecção de tabelas, mais lento, para quando a estrutura tabular importa
- Destino configurável, na mesma pasta do original ou em pasta escolhida
- Nunca sobrescreve arquivo existente

## Formatos aceitos

PDF, DOCX, DOC, PPTX, XLSX, XLS, CSV, HTML, TXT, RTF, EPUB, JSON, XML, ZIP e imagens PNG e JPG, estas com reconhecimento óptico.

## Instalação

Requer Python 3.10 ou superior.

```
pip install -r requirements.txt
```

Ou, sem clonar o repositório:

```
pip install pypdfium2 "markitdown[all]"
```

## Uso

Duplo clique em `conversor_markdown.pyw`. A extensão `.pyw` evita a janela de console.

Na janela, clique em "Escolher arquivos", selecione o que precisa converter, ajuste as opções e clique em "Converter". A tecla `Delete` remove itens da lista.

Se o duplo clique abrir um editor de texto, clique com o botão direito no arquivo, escolha "Abrir com", depois "Escolher outro aplicativo", e selecione o `pythonw.exe` da sua instalação do Python.

## Desempenho

O ganho de velocidade veio da troca do motor de PDF. O MarkItDown usa `pdfminer.six` e `pdfplumber`, precisos e muito lentos. Este programa usa o PDFium para o modo padrão e recorre ao MarkItDown apenas quando a detecção de tabelas é solicitada.

Medição em PDF sintético de 300 páginas de texto denso.

| Motor | Tempo | Texto extraído |
|---|---|---|
| pdfminer.six | 21,90s | 185.099 caracteres |
| PDFium (`pypdfium2`) | 0,24s | 184.499 caracteres |

Cerca de 90 vezes mais rápido, com o mesmo conteúdo.

Em três processos reais, com o rodapé removido, os arquivos ficaram entre 18% e 23% menores. A verificação por saco de palavras confirmou que a redução veio apenas do rodapé. Em um dos processos, o `pdfminer.six` deixou de extrair 231 blocos que o PDFium capturou.

## Limitações conhecidas

O programa extrai texto. Ele não faz reconhecimento óptico de PDF digitalizado. Se o PDF for imagem pura, o resultado vem vazio.

A detecção de tabelas do modo alternativo é razoável, não perfeita. Tabelas com células mescladas ou bordas irregulares saem imprecisas.

Os padrões de remoção de rodapé foram calibrados para o PJe do TJDFT. Outros tribunais usam carimbos diferentes. A lista de expressões regulares fica na constante `PADROES_RODAPE`, no início do arquivo, e é fácil de estender.

A interface foi testada no Windows. Deve funcionar no macOS e no Linux, onde o `tkinter` estiver disponível, mas isso não foi verificado.

## Licenças

Este projeto está sob licença MIT. Veja o arquivo `LICENSE`.

| Dependência | Licença |
|---|---|
| `pypdfium2` | BSD-3-Clause e Apache-2.0 |
| `markitdown` | MIT |

O PyMuPDF foi deliberadamente evitado. Ele é mais rápido, mas tem licença AGPL-3.0 ou comercial, e o copyleft se estenderia a este projeto e a qualquer derivado.

## Aviso sobre dados

O `.gitignore` bloqueia `.md`, `.pdf`, `.docx` e formatos correlatos, justamente para impedir que documento processado entre no repositório por acidente. Antes de qualquer `commit`, confira com `git status` o que será enviado.
