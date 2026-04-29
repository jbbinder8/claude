# Contexto do repositório — leia antes de qualquer ação git

## Estrutura de repositórios remotos

| Remote | URL | Visibilidade | Conteúdo |
|--------|-----|--------------|----------|
| `origin` | https://github.com/jbbinder8/claude | **Privado** | Todos os projetos desta pasta |
| `siconfi-public` | https://github.com/jbbinder8/siconfi_receitas | **Público** | Apenas `siconfi_receitas/` |

## Regras de push

- `git push origin master` → repositório **privado** (`claude`). Use para commits normais.
- O repositório público **NÃO é atualizado automaticamente**. Para publicar alterações em `siconfi_receitas/`:

```bash
git subtree push --prefix=siconfi_receitas siconfi-public master
```

> Nunca torne o repositório `origin` público — os demais projetos da pasta são privados.

## Projetos nesta pasta

| Pasta / Arquivo | Descrição |
|-----------------|-----------|
| `siconfi_receitas/` | Extrator de receitas fiscais (ICMS, ISS, Cota-Parte ICMS) via SICONFI/DCA, RREO e SIOPS — **público** em `siconfi-public` |
| `siconfi_dca/` | Extrator DCA SICONFI |
| `siconfi_dca_downloader.py` | Downloader DCA |
| `cosmic_web/` | Simulação de teia cósmica |
| `converter_pdf/` | Utilitário de conversão PDF |
| `simulador_patrimonio.html` | Simulador de patrimônio |
| `output/` | Dados gerados — não comitar arquivos grandes |
