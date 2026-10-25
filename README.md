# web_common

`web_common` contiene los componentes compartidos por `MiniBrowser` y `WebAgent`.
Los proyectos siguen siendo aplicaciones independientes y mantienen sus puntos
de entrada; cada uno importa aquí solo las piezas que necesita.

## Estructura

- `browser/`: pestañas, panel lateral y perfiles WebEngine.
- `nav/`: barra de direcciones y acciones de navegación.
- `storage/`: rutas de datos, almacenes JSON, historial y sesiones.
- `viewers/`: visores locales y sus recursos estáticos en `viewers/assets/`.
- `downloads/`: entrega de URLs al Downloader.
- `runtime/`: coordinación de instancias únicas.

MiniBrowser y WebAgent importan los componentes directamente desde estos
subpaquetes, por lo que las rutas reflejan la responsabilidad de cada módulo.

## Componentes principales

- `browser/tabs.py`: pestañas WebEngine, ventanas emergentes con pestañas y menú
  contextual común (sonido y cierre de pestañas), incluida la configuración
  del ciclo de vida del `QTabWidget` mediante `configure_tab_widget()`. Las
  ventanas emergentes de login de Google se cierran automáticamente cuando su
  única pestaña llega a `https://accounts.google.com/gsi/transform`.
- `nav/navbar.py`: barra de navegación, conversión de direcciones y guardado de
  páginas.
- `browser/web_profiles.py`: creación de perfiles aislados de Qt WebEngine. Usa un
  User-Agent compatible con WhatsApp tanto en JavaScript como en las cabeceras
  de red, y aplica el reemplazo por host mediante un interceptor;
  `build_web_profile(..., site_user_agents=...)` permite reemplazar ese mapa.
- `storage/session.py`: restauración, metadatos y persistencia de sesiones.
  `save_tab_session(..., include_blank=True)` permite a una aplicación persistir
  pestañas `about:blank` intencionales junto con metadatos propios de la app.
- `viewers/local_viewer.py` y `viewers/folder_viewer.py`: archivos locales, carpetas,
  edición, Git y navegación dentro de archivos comprimidos. `archive_entries()`
  lista contenidos y `extract_archive()` extrae ZIP, TAR/GZIP/BZIP2 y, cuando
  están instaladas sus dependencias opcionales, RAR/7z.
- `viewers/video_tab.py` y `viewers/epub_tab.py`: visores locales; `video_tab.py` también
  expone `open_video_tab()` para crear y registrar una pestaña de video.
- `viewers/yt_dlp_tab.py`: reproducción y descarga de URLs reconocidas por
  extractores específicos instalados de yt-dlp. La opción aparece en el menú
  contextual de la pestaña; la descarga pregunta dónde guardar el archivo.
  El extractor genérico se excluye para evitar mostrar la opción en cualquier
  URL. Requiere instalar `yt-dlp` en el mismo entorno Python que MiniBrowser.
  Requiere FFmpeg en `PATH`, junto al punto de entrada, o configurado mediante
  `FFMPEG_LOCATION`. FFmpeg combina audio y video separados durante la
  reproducción inmediata de lives y transcodifica a H.264/AAC para evitar
  incompatibilidades AV1 de Qt Multimedia. Las descargas remuxan a MKV por
  defecto. Si el formato principal es solo video, se selecciona la mejor pista
  de audio disponible. YouTube puede omitir `acodec` aunque yt-dlp marque el
  formato como `audio only`; ese indicador también se usa para mapear la pista
  a FFmpeg. Si no se obtiene una pista, se informa en vez de reproducir en silencio.
  La lista oficial de extractores está en
  [yt-dlp supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md);
  la compatibilidad real puede cambiar por sitio. La reproducción depende de
  los formatos y codecs admitidos por Qt Multimedia.
- `storage/history.py`: persistencia SQLite y diálogo del historial agrupado por
  sesión de navegación.
- `browser/sidebar.py` y `downloads/downloader_handoff.py`: paneles compartidos y entrega de
  descargas al Downloader.
- `browser/sidebar.py` conserva los favicon de las aplicaciones en el campo `favicon`
  de cada entrada. Conectá `SidebarRail.on_favicon_changed` a
  `JsonListStore.update_item` para guardar el valor en disco.
- `nav/navigation.py`: ajuste y restablecimiento del zoom de la vista activa,
  pestaña activa, activación de la pestaña `+`, sincronización
  de la barra de dirección y carga de URLs con callbacks específicos.
- `browser/tabs.py`: `BLOCKED_URLS` contiene prefijos de URLs que no deben navegar ni
  abrir pestañas nuevas; agregá nuevos destinos bloqueados a esa lista.
- `viewers/assets/epub_reader.html`, `epub_reader.css` y `epub_reader.js`: plantilla
  y comportamiento del lector EPUB, separados del código Python.
- `viewers/assets/local_viewer.html`, `local_viewer.css`, `archive_viewer.html`,
  `archive_viewer.css` y `archive_viewer.js`: plantillas y recursos para
  mensajes locales y listados de comprimidos.
- `viewers/assets/folder_viewer.html`, `folder_viewer.css` y `folder_viewer.js`:
  plantilla, estilos y comportamiento del explorador de carpetas y archivos.
- `browser/tabs.py` también expone `close_tab()`, que centraliza el cierre seguro,
  selección de la pestaña anterior y recreación de una pestaña cuando solo
  queda `+`; cada aplicación inyecta su limpieza particular.
- `viewers/local_file_types.py`: clasificación de extensiones locales. Mantiene esta
  decisión fuera de `folder_viewer.py` para que las pestañas WebEngine no
  dependan del explorador/editor de carpetas.

`downloads/downloader_handoff.py` también expone el handoff explícito de una URL
actual. Las ventanas pueden conectarlo a su barra sin interceptar navegación normal.

`WebAgent` y `MiniBrowser` deben mantener en sus ventanas únicamente los callbacks y
metadatos propios de cada aplicación. El historial compartido se instancia con
`HistoryStore` y se muestra con `HistoryDialog`. La creación de pestañas, la barra `+`,
el cierre seguro, el reordenado y los eventos comunes se conectan mediante
`configure_tab_widget()`. Los gestores de perfiles, sesiones de negocio,
descargas, colecciones y páginas de inicio siguen siendo específicos de cada
aplicación.

## Menú de pestañas

Usá `install_tab_context_menu()` desde la ventana que posee el
`QTabWidget`. La ventana sigue siendo responsable de cerrar sus widgets y de
mantener cualquier pestaña especial, como la pestaña `+`; el helper solo
construye las acciones comunes.

Los cambios en esta carpeta pueden afectar simultáneamente a MiniBrowser y
WebAgent. Conservá las importaciones relativas y la capacidad de ejecutar
cada aplicación directamente desde su propio directorio.

## Organización interna

`viewers/video_tab.py` contiene tanto `VideoTab` como `open_video_tab()`, y
`viewers/local_file_types.py` contiene la clasificación de archivos de texto.
Los consumidores deben importar las implementaciones desde los subpaquetes.
