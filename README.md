# 🎓 Portal Web Institucional y Asistente Virtual Híbrido — IES N° 11

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit&logoColor=white)
![Google Gemini](https://img.shields.io/badge/IA-Google%20Gemini%20API-8E75B2?logo=googlegemini&logoColor=white)
![Google Sheets](https://img.shields.io/badge/Base%20de%20Datos-Google%20Sheets%20API-34A853?logo=googlesheets&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![Costo Operativo](https://img.shields.io/badge/Costo%20Operativo-%240%20(Free%20Tier)-success)

> **Trabajo Final Integrador · EDI II - Ciencias de Datos**  
> **Carrera:** Tecnicatura Superior en Ciencia de Datos e Inteligencia Artificial  
> **Institución:** Instituto de Educación Superior N° 11 (Alvear 1145, San Salvador de Jujuy, Argentina)

---

## 📋 Descripción del Proyecto

Este proyecto consiste en el diseño, desarrollo, integración y evaluación de un **Portal Web Institucional** para el **IES N° 11** que incorpora un **Asistente Estudiantil Virtual de arquitectura híbrida** y un **sistema de telemetría en tiempo real** enfocado en la mejora continua mediante Ciencia de Datos.

### 🎯 El Problema que Resuelve
1. **Sobrecarga operativa en Secretaría:** Descomprime las consultas repetitivas durante períodos críticos (inscripciones, mesas de examen, pases y equivalencias).
2. **Barrera de "jerga institucional" y horario limitado:** Guía a ingresantes y aspirantes las 24 horas en lenguaje claro y rioplatense sobre conceptos del nivel superior (*regularidad, correlatividades, promoción, condición libre*), fuera del horario presencial de secretaría (lunes a viernes de 08:00 a 23:00 hs).
3. **Administración *Zero-Code*:** Permite al personal administrativo actualizar fechas, requisitos y enlaces directamente desde una planilla de **Google Sheets** sin tocar código.
4. **Auditoría de fallos y Mejora Continua:** Captura cada interacción y calificación del estudiante (`LIKE` / `DISLIKE`) para diagnosticar vacíos de conocimiento (`hubo_fallo = 'SI'`) y perfeccionar las respuestas del bot. La columna `origen` (`TEXTO` / `VOZ` / `BOTON`) permite separar los vacíos de contenido de los posibles errores de transcripción de las consultas habladas.

---

## ✨ Características y Arquitectura Principal

* 🌐 **Portal Web + Interfaz Conversacional (Streamlit):** Diseño adaptable a dispositivos móviles y escritorio con identidad institucional, barra lateral con datos de contacto en SVG, preguntas frecuentes (FAQ), migas de pan (*breadcrumbs*) y medidor de cuota de IA.
* ⚡ **Motor de Ruteo Híbrido:**
  * **Navegación Determinística y Búsqueda Léxica (`uso_ia = NO`):** Resuelve clics en tarjetas, comandos numéricos y búsquedas rápidas en **0 segundos** sin consumir cuota de API.
  * **Asesor Conversacional con IA (`uso_ia = SI`):** Atiende consultas abiertas o complejas en modo *streaming* utilizando **Google Gemini API** bajo un enfoque **RAG Ligero** (inyectando únicamente los nodos activos en `<informacion_oficial>`).
* 🎙️ **Consultas por voz:** el alumno puede hablarle al asistente desde el micrófono integrado en la caja de texto (`st.chat_input(accept_audio=True)`). El audio se transcribe con Gemini, el texto entendido se muestra en el chat con el ícono 🎙️ (para que el alumno vea qué entendió el bot) y sigue el mismo ruteo híbrido que una consulta escrita. Cada audio consume la misma cuota compartida de IA y cuenta como una consulta de la sesión.
* 📎 **Botones de descarga relevantes:** junto a cada respuesta de IA solo aparecen los archivos que tienen que ver con lo consultado. Las filas de la planilla con muchos links (catálogos, p. ej. una cartilla por carrera) aportan únicamente las carreras que la pregunta o la respuesta nombran, ordenadas según se las menciona y rotuladas con el título del catálogo (*"Cartillas de Ingreso 2026: Hotelería"*), aunque la IA no haya citado esa fila.
* 🧹 **Texto limpio:** las citas internas que el modelo deja sueltas en el texto (`[id:5.10]`, `[3.6, 5]`) se quitan de la respuesta, también mientras se escribe en vivo, y siguen contando como fuentes oficiales.
* 🛡️ **Blindaje Anti-Alucinación:** Regla estricta en el *prompt* del sistema que prohíbe inventar fechas, requisitos o enlaces. Si el dato no figura en la planilla oficial, el asistente declara explícitamente el desconocimiento, deriva a Secretaría y activa la alerta `hubo_fallo = 'SI'`.
* 📊 **Telemetría Asíncrona y RLHF (*In-Place*):** Guardado en segundo plano (`threading.Thread`) de 9 variables en Google Sheets y captura de retroalimentación humana (`st.feedback`) que actualiza la fila original sin duplicar registros.
* 🔍 **Pipeline de Ciencia de Datos:** Procesamiento con `Pandas`, `NLTK`, `Matplotlib` y `Seaborn` para auditar tasas de fallo, analizar palabras clave no reconocidas (NLP) y proyectar el Dashboard de mejora continua.

---

## 🗄️ Arquitectura de Datos (Google Sheets)

El sistema utiliza una hoja de cálculo en Google Cloud dividida en tres pestañas independientes, leídas con caché inteligente (`@st.cache_data(ttl=300)`):

### 1. Pestaña `Menu` (Base de Conocimiento Jerárquica)
Almacena el árbol de decisión interactivo y el contexto oficial del instituto:
| Variable | Tipo | Descripción |
| :--- | :--- | :--- |
| `id` | String (PK) | Identificador único del nodo (ej. `ROOT`, `1`, `5.4`). |
| `padre_id` | String (FK) | ID del nodo superior (`ROOT` o vacío para nivel principal). |
| `opcion` | String | Código corto visible para navegación rápida en el chat. |
| `titulo` | String | Nombre de la categoría, carrera o trámite. |
| `palabras_clave` | String | Sinónimos y términos clave para el motor de búsqueda léxica. |
| `respuesta` | Markdown | Texto oficial que se muestra al alumno y alimenta a Gemini. |
| `link_url` | URL | Enlaces a formularios o cartillas (separados por `\|`). |
| `link_texto` | String | Etiqueta de los botones de descarga asociados a `link_url`. |
| `activo` | Booleano | Flag (`si` / `no`) para activar u ocultar nodos sin borrar filas. |

> 📌 **Filas con muchos links (catálogos).** Una fila con **más de 5 links** se trata como un catálogo (p. ej. `3.6 · Cartillas de Ingreso 2026`, con una cartilla por carrera): cuando responde la IA, solo se muestran los archivos cuyo nombre aparece en la consulta o en la respuesta. Por eso conviene que cada texto de `link_texto` **nombre el documento** (`Hotelería`, `Ciencias de Datos e IA`) y no sea genérico (`Descargar archivo`). Las filas con hasta 5 links se muestran completas. Para el menú navegable (sin IA) siguen apareciendo todos los links de la fila.

### 2. Pestaña `Config` (Parámetros Globales)
Pares `clave / valor` para personalizar en vivo: `nombre_ies`, `descripcion`, `mensaje_bienvenida`, `direccion`, `horarios`, `telefono`, `email`, `sitio_web`, `preguntas_frecuentes` y `aviso_ia`.

### 3. Pestaña `Logs_Bot` (Dataset de Telemetría — 9 Columnas)
Cada interacción (exceptuando comandos de retorno `0` y `#`) registra una fila con la siguiente estructura:
| Col. | Variable | Tipo | Propósito Analítico |
| :---: | :--- | :--- | :--- |
| **A** | `fecha_hora` | Datetime | Marca temporal (`YYYY-MM-DD HH:MM:SS`) para mapas de calor horarios. |
| **B** | `id_sesion` | String (8 chars) | Hash anónimo (`uuid4()[:8]`) para trazar el recorrido sin datos personales. |
| **C** | `texto_alumno` | String ($\le 200$) | Consulta textual ingresada o tarjeta seleccionada por el estudiante. |
| **D** | `nodo_detectado`| String | ID del nodo consultado (`ROOT` en búsquedas globales). |
| **E** | `uso_ia` | `SI` / `NO` | Distingue respuestas de Google Gemini frente al motor léxico/menú. |
| **F** | `hubo_fallo` | `SI` / `NO` | **Variable crítica:** marca `SI` ante vacío de búsqueda léxica o desconocimiento de IA. |
| **G** | `respuesta_bot` | String ($\le 200$) | Extracto limpio de la respuesta real entregada para auditoría de calidad. |
| **H** | `feedback` | `LIKE` / `DISLIKE` | Valoración del estudiante actualizada *in-place* sobre la misma fila. |
| **I** | `origen` | `TEXTO` / `VOZ` / `BOTON` | Cómo llegó la consulta: escrita, hablada o por clic en una tarjeta/menú. Permite separar fallos de contenido (`TEXTO`) de posibles errores de transcripción (`VOZ`). |

> ⚙️ **Al migrar una planilla existente** hay que escribir el encabezado `origen` en la celda `I1` de `Logs_Bot` (el guardado usa `append_row`, por lo que la columna nueva se agrega sola al final de cada fila).
>
> 🎙️ **Reglas del registro de voz:**
> * En `texto_alumno` se guarda la transcripción **anonimizada** (se aplica `anonimizar_consulta`; si queda vacía se registra `(consulta de voz)`), porque al hablar es más fácil dictar nombres o números de documento sin querer.
> * Los audios que **no se pudieron transcribir** (sin voz, demasiado largos, sin cuota o sin conexión) **no generan fila**: no son consultas al bot y ensuciarían la tasa de fallos. Solo quedan en el log técnico de la aplicación, sin contenido.
> * El audio nunca se guarda: se envía a Gemini únicamente para transcribirlo.
> * Para el dashboard, calcular las consultas no resueltas con `origen = TEXTO` y analizar `VOZ` por separado.

---

## 🛠️ Stack Tecnológico

* **Frontend & Web:** Portal Web Institucional + Python `Streamlit`
* **Motor LLM:** `google-genai` / Google Gemini API (respuestas en *streaming* y transcripción de audio, con el mismo cliente, los mismos modelos con *failover* y los mismos límites compartidos de cuota — `ControlLLM`)
* **Entrada de voz:** micrófono nativo de `st.chat_input(accept_audio=True)` (requiere **Streamlit ≥ 1.52**)
* **Persistencia y Concurrencia:** `gspread`, `google-auth`, `threading`
* **Ciencia de Datos y NLP:** `pandas`, `nltk`, `matplotlib`, `seaborn`
* **Infraestructura:** `Docker` & Entornos Virtuales (`venv`)

---

## 🚀 Instalación y Ejecución Local

### 1. Clonar el repositorio
```bash
git clone https://github.com/gonzarratia/ChatBot_IES11.git
cd ChatBot_IES11
```

### 2. Crear y activar el entorno virtual
```bash
# En Windows (Git Bash / MINGW64)
python -m venv venv
source venv/Scripts/activate
```

### 3. Instalar las dependencias
```bash
pip install -r requirements.txt
```
> La entrada de voz requiere `streamlit>=1.52`. Ya **no** se usan `streamlit-mic-recorder` ni `google-generativeai` (SDK anterior): todo el acceso a Gemini pasa por `google-genai`. Si usás Docker, reconstruí la imagen (`docker compose up --build -d`) tras actualizar `requirements.txt`.

### 4. Configurar las credenciales y variables de entorno
Crea el archivo `.streamlit/secrets.toml` (o configura tus variables de entorno) con tu API Key de Google Gemini, el ID de la planilla de Google Sheets y las credenciales de tu *Service Account* de Google Cloud:

```toml
# .streamlit/secrets.toml
GEMINI_API_KEY = "TU_API_KEY_DE_GEMINI"
SHEET_ID = "ID_DE_TU_GOOGLE_SHEET"

[gcp_service_account]
type = "service_account"
project_id = "tu-proyecto-gcp"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "tu-service-account@tu-proyecto-gcp.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```
> ⚠️ **Importante:** Asegúrate de que `.streamlit/secrets.toml`, archivos `.env` y credenciales `.json` estén incluidos en tu `.gitignore` para no subir claves privadas a GitHub.

### 5. Ejecutar la aplicación
```bash
streamlit run app.py
```

### 6. Requisitos para usar el micrófono
* El navegador solo permite el micrófono en **HTTPS o en `localhost`**. Publicado por `http://IP:8501` en una red local el botón aparece, pero no graba.
* La primera vez el navegador pide permiso; si se denegó, habilitarlo desde el candado de la barra de direcciones (*Configuración del sitio → Micrófono*).
* Duración máxima por audio: **≈ 1 minuto** (2 MB de WAV). La transcripción se recorta a 200 caracteres, igual que el cuadro de texto.
* Conviene agregar a `aviso_ia` (pestaña `Config`) una frase como: *«Si usás el micrófono, el audio se envía a Google para transcribirlo y no se guarda.»*


---

## 🔒 Ética, Privacidad y Uso Responsable de IA

* **Privacidad por Diseño:** El asistente advierte expresamente en la interfaz no ingresar datos personales sensibles (DNI, teléfono, domicilio) y utiliza identificadores de sesión efímeros y anónimos (`id_sesion` de 8 caracteres).
* **Voz y privacidad:** el audio se envía a Google (Gemini) solo para transcribirlo y no se almacena. Antes de guardarse en `Logs_Bot`, la transcripción se anonimiza. La interfaz advierte al alumno que no dicte datos personales.
* **Supervisión Humana (*Human-in-the-Loop*):** El sistema actúa como primer nivel de orientación pública y deriva casos particulares a Secretaría. El equipo directivo y técnico audita periódicamente los registros con `hubo_fallo = 'SI'` o `feedback = 'DISLIKE'` para actualizar la planilla institucional.

---

## 🩺 Solución de Problemas

| Síntoma | Causa probable | Qué hacer |
| :--- | :--- | :--- |
| Al grabar, la línea queda plana y al tocar ✓ dice **«Recording failed»** | El navegador no capturó audio (micrófono equivocado, silenciado o tomado por otra app) o falló la subida del audio | Abrir la consola del navegador (F12) y buscar `Recording error:` o `Audio upload failed:`. Probar `streamlit run test_mic.py`: si ahí también falla, es del navegador/micrófono (elegir el micrófono correcto en el candado de la barra de direcciones, revisar *Sonido → Entrada* y *Privacidad → Micrófono* en Windows, cerrar Zoom/Teams/Discord/OBS, probar sin auriculares Bluetooth, otro navegador o ventana de incógnito). |
| El botón de micrófono aparece pero no graba | Se accede por `http://IP:puerto` | Usar HTTPS o `localhost`. |
| No aparece el botón de micrófono | Streamlit < 1.52 o IA no disponible (sin clave / sin cuota) | Actualizar Streamlit y revisar `GEMINI_API_KEY`. |
| «Ahora no puedo procesar audios» | Cuota de Gemini agotada o sin conexión | Esperar un minuto o escribir la consulta; el bot no registra ese intento. |
| La columna `origen` no aparece en `Logs_Bot` | Falta el encabezado en `I1` | Escribir `origen` en la celda `I1`. |
| Un botón de descarga no aparece tras una respuesta de IA | La fila es un catálogo (> 5 links) y ningún `link_texto` nombra lo que se consultó | Nombrar cada link con el documento o carrera (`Hotelería`, no `Descargar archivo`). |

---

## 🔭 Limitaciones Conocidas y Trabajo Futuro

* **Calidad de la transcripción:** una consulta hablada mal transcripta puede figurar como `hubo_fallo = 'SI'` aunque el contenido exista; por eso se registra el `origen`. No hay medición automática de la confianza de la transcripción.
* **Audios fallidos sin registro:** hoy no se guardan; si se quiere medir cuántos fallan, se puede sumar una pestaña aparte (`Logs_Voz`) con solo fecha y motivo, sin tocar `Logs_Bot`.
* **Cuota de IA por voz:** una pregunta hablada que además se responde con IA consume **dos** consultas de la sesión (transcripción + respuesta) y dos de la cuota global.
* **Descargas en catálogos:** dependen de que el nombre del link coincida con cómo la respuesta nombra la carrera; un texto genérico en `link_texto` no se puede relacionar con la consulta.

---

## 👥 Equipo de Desarrollo

Proyecto desarrollado para la cátedra **EDI II - Ciencias de Datos** del **Instituto de Educación Superior N° 11** (San Salvador de Jujuy):

* **Gonzalo Arratia** 
* **Marcos Mamani**
* **Adrián Mamani**
* **Fernanda Luquet**
* **Justina Ramos**

---
*Instituto de Educación Superior N° 11 · Alvear 1145, San Salvador de Jujuy, Jujuy, Argentina.*
