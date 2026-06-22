# locais

| Propósito | Caminho |
|-----------|---------|
| Python (3.13.3, 64-bit) | `C:\Program Files\Python313\python.exe` |
| pip | `C:\Program Files\Python313\python.exe -m pip` |

> Nesta máquina (usuário `03686846950`), `python` e o launcher `py` **estão no PATH**
> e resolvem para o Python 3.13.3 acima. Mesmo assim, prefira o caminho completo em
> scripts para evitar o stub do Microsoft Store em `WindowsApps`.
>
> Pacotes científicos instalados: `numpy`, `scipy`, `pandas`, `pyarrow`, `matplotlib`.
>
> O console usa cp1252: exporte `PYTHONUTF8=1` ao imprimir caracteres unicode
> (✓, ≈, etc.) para evitar `UnicodeEncodeError`.


# Contexto do repositório — leia antes de qualquer ação git

## Repositório remoto

| Remote | URL | Visibilidade |
|--------|-----|--------------|
| `origin` | https://github.com/jbbinder8/claude | **Público** |

## Regras de push

- `git push origin master` → único repositório remoto. Use para todos os commits.
