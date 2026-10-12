<p align="right"><a href="README.md">English</a> · <b>Español</b></p>

# cite-or-silence

Haz una pregunta de filosofía y recibe una respuesta construida solo con la
[Stanford Encyclopedia of Philosophy](https://plato.stanford.edu/). Cada frase enlaza a la sección
exacta de la que sale, cada cita se comprueba automáticamente y, si la SEP no cubre la pregunta, la
respuesta es **«No lo sé»**. Se puede preguntar en español; la SEP está en inglés.

Sin búsqueda, un tercio de lo que dice un modelo sobre filosofía no está en la SEP. Con búsqueda y
verificación, casi nada (ver [Resultados](#resultados) y [dónde falla](#dónde-falla)).

https://github.com/user-attachments/assets/951ef46d-f069-4b51-8a91-35c9ab4d587d

## Qué se mide

| Métrica | Qué pregunta responde |
|---|---|
| Recall@5 | ¿La búsqueda encontró la sección correcta? |
| Precisión de las citas | ¿Cada cita respalda su frase? |
| Fidelidad | ¿La respuesta se queda dentro de lo que cita? |
| Acierto al callar | ¿Dice «no lo sé» cuando debe? |

El titular es una comparación: el mismo modelo sin búsqueda frente a con búsqueda y comprobación de
citas.

## Resultados

101 preguntas escritas antes de que existiera el sistema de búsqueda: 81 que la SEP permite responder
(51 con una sola entrada, 30 que necesitan varias), 15 que no cubre y 5 que parten de una premisa
falsa. Cada modelo responde de tres maneras: **de memoria**, **con RAG** (con diez pasajes
recuperados, antes de la verificación) y **verificada** (lo que sobrevive a la comprobación de
citas). El juez es el mismo modelo que responde, y califica a ciegas las tres respuestas frente a las
secciones de referencia más los pasajes recuperados.

| | codex:gpt-6-luna:low | | | ollama:qwen3:14b | | |
|---|---:|---:|---:|---:|---:|---:|
| | **de memoria** | **con RAG** | **verificada** | **de memoria** | **con RAG** | **verificada** |
| Frases respaldadas por la SEP | 66 % | 99 % | **100 %** | 59 % | 93 % | **96 %** |
| Frases sin respaldo | 33 % | 1 % | **0 %** | 39 % | 5 % | **3 %** |
| Frases que la SEP contradice | 1 % | 1 % | 0 % | 1 % | 1 % | 1 % |
| Preguntas con respuesta en las que calla | 0 % | 1 % | 7 % | 54 % | 1 % | 1 % |
| Preguntas fuera de la SEP que no contesta (15) | 80 % | 100 % | 100 % | 93 % | 100 % | 100 % |
| Premisas falsas corregidas (5) | 5/5 | 1/5 | 0/5 | 0/5 | 0/5 | 0/5 |

Los porcentajes de frases son sobre las preguntas con respuesta. El juez es indulgente (siguiente
sección), así que las tasas de respaldo son cotas superiores: el hallazgo es la distancia entre «de
memoria» y «verificada», no los porcentajes exactos.

## Comprobar al comprobador

El juez del banco de pruebas califica cada frase de una respuesta como respaldada, sin respaldo o
contradicha por la SEP. Antes de fiarse de sus números, se sacaron 100 de sus calificaciones
(estratificadas por etiqueta, la mitad de codex:gpt-6-luna:low y la otra mitad de ollama:qwen3:14b) y
se revisaron otra vez, a ciegas.

**Un segundo modelo** (Claude Opus 5.5) coincidió en 65 de 70 calificaciones «respaldada» y en 17 de
29 «sin respaldo». Donde discrepan, el indulgente es el juez: da por buenas frases que conservan la
idea de un pasaje pero pierden quién lo dijo («possible worlds are…» para lo que el pasaje presenta
como la postura de Leibniz) o amplían su alcance («contemporary feminists» para «pragmatist and
continental feminists»).

**Una persona sin formación en filosofía** revisó 20 y aceptó 19, entre ellas cinco que tanto el juez
como el segundo modelo habían rechazado.
Cuando una frase llevaba cita, la cita parecía correcta, y lo era: el modelo había encontrado el
pasaje correcto y luego lo había estirado al escribir la frase.

Así que enseñarle una cita al lector no basta: una cita correcta bajo una frase que no respalda se lee
como una prueba. Para eso está la verificación. Sobre las 64 frases revisadas que llevaban cita, el
juez de verificación (codex:gpt-6-luna:low) tachó 4 o 5 de las 6 que el segundo modelo encontró sin
respaldo, y tachó por error 7 de 53 que los dos revisores dieron por respaldadas.
Un prompt de verificación más estricto (rechazar también atribuciones perdidas, alcances ampliados y
explicaciones invertidas) no atrapó ninguna frase mala más y tachó 12 buenas, así que no se adoptó.
`scripts/verifier_cases.py` repite esta comprobación.

## Dónde falla

- **Premisas falsas.** Una frase como «la premisa es falsa» no tiene pasaje que citar, así que la
  verificación la tacha. Codex de memoria corrigió las 5 premisas falsas; verificado, no corrige
  ninguna.
- **Preguntas en español, enciclopedia en inglés.** La búsqueda pone una sección de referencia entre
  las 5 primeras en el 51 % de las preguntas (30 % cuando la respuesta abarca varias entradas), aunque
  la entrada correcta está ahí el 80 % de las veces. Las respuestas verificadas citan la sección de
  referencia en el 30 % (codex) y el 51 % (qwen) de las preguntas: la mayoría están respaldadas, pero
  por una sección vecina y no por aquella para la que se escribió la pregunta.
- **Callar tiene un coste.** El verificador tacha alrededor de 1 de cada 8 frases que los revisores
  dieron por respaldadas (ver arriba), y codex verificado no contesta nada en el 7 % de las preguntas
  con respuesta.
- **El juez es el mismo modelo que responde**, y deja pasar frases que pierden quién sostiene una
  postura o amplían su alcance. Con otro juez, los números podrían ser más bajos en todas las filas.
- **Muestra pequeña.** 101 preguntas; la fila de premisas falsas se apoya en cinco.

## Cómo funciona

1. **Descargar** cada entrada de la SEP, una petición cada 5 segundos (como pide su robots.txt).
2. **Trocear** por sección (§1, §2.3…) y párrafo; cada fragmento guarda un enlace a su sección.
3. **Buscar** con embeddings multilingües más BM25, guardados en DuckDB.
4. **Responder y verificar**: cada frase cita un fragmento; una segunda pasada comprueba que la cita
   existe y respalda la frase. Las frases que fallan se tachan.
5. **Evaluar** con ~100 preguntas escritas antes de que existiera el sistema de búsqueda.

## Ponerlo en marcha

```bash
uv sync
uv run cite-or-silence fetch      # ~2,5 h, una sola vez
uv run cite-or-silence chunk
uv run pytest
uv run cite-or-silence serve      # http://127.0.0.1:8765: pregunta y mira cómo se comprueba cada frase
```

La página enseña los pasajes que encontró la búsqueda, el borrador del modelo con una cita junto a
cada frase y la verificación, que mantiene o tacha cada una. Solo escucha en tu máquina: muestra texto
de la SEP, que se puede leer pero no republicar.

## Sobre el texto de la SEP

La SEP permite rastrear sus entradas para indexarlas, pero no redistribuirlas. Este repositorio no
contiene texto de la SEP: el corpus, los fragmentos y el índice se construyen en tu máquina y nunca se
suben al repositorio. Por favor, apoya a la SEP: https://plato.stanford.edu/support/

## Licencia

Código: MIT. Las entradas de la SEP siguen bajo las condiciones de la propia SEP.
