# Instrucciones para subir a GitHub

> Estos pasos los hace **Owen** desde su terminal local — no requieren
> credenciales en este entorno.

## 1. Crear el repositorio en GitHub

Ir a https://github.com/new y crear:

| Campo            | Valor                                |
|------------------|--------------------------------------|
| Owner            | (tu cuenta)                          |
| Repository name  | `vivacolombia-lakehouse`             |
| Description      | Mini-Lakehouse VivaColombia · Taller #3 ITM 2026 |
| Visibility       | Public                               |
| Initialize       | **NO** (no agregar README ni .gitignore — ya están) |

Anotar la URL HTTPS o SSH que GitHub muestra al final.
Ejemplo: `https://github.com/<usuario>/vivacolombia-lakehouse.git`

## 2. Inicializar Git localmente y hacer el primer commit

Desde la carpeta `vivacolombia-lakehouse/`:

```bash
git init
git config user.name  "Owen David Pérez Sánchez"
git config user.email "owen@blackroom.com.co"

git add .
git status                       # revisar qué se va a commitear
git commit -m "Taller #3 - Mini-Lakehouse VivaColombia (entrega inicial)"
```

## 3. Conectar al repo remoto y hacer push

```bash
git branch -M main
git remote add origin https://github.com/<usuario>/vivacolombia-lakehouse.git
git push -u origin main
```

Si GitHub pide autenticación, usar **Personal Access Token (PAT)** —
no la contraseña de la cuenta. Generarlo en
https://github.com/settings/tokens (scope: `repo`).

## 4. Tag de la entrega

Una vez subido todo:

```bash
git tag -a v1.0 -m "Entrega Taller #3 — VivaColombia Mini-Lakehouse"
git push origin v1.0
```

## 5. Compartir con el docente

Enviar al docente **Roberto Carlos Rahamut Suteu** el link:

```
https://github.com/<usuario>/vivacolombia-lakehouse
```

Si el repo es privado, agregar al docente como colaborador:
*Settings → Collaborators → Add people*.

## 6. Verificación rápida desde clone limpio

Para confirmar que la rúbrica de "Reproducibilidad" se cumple:

```bash
# En otra carpeta o máquina:
git clone https://github.com/<usuario>/vivacolombia-lakehouse.git
cd vivacolombia-lakehouse
pip install -r requirements.txt
python main.py
```

Debería completar en ~10-30s y dejar Parquets en `lakehouse/gold/`.
