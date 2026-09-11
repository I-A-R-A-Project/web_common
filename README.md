# web_common

`web_common` contiene los componentes compartidos por `MiniBrowser`, `WebAgent` y
`ArtVision`. Los proyectos siguen siendo aplicaciones independientes y
mantienen sus puntos de entrada; cada uno importa aquí solo las piezas que
necesita.

## Componentes principales

- `tabs.py`: pestañas WebEngine, ventanas emergentes con pestañas y menú
  contextual común (sonido y cierre de pestañas), incluida la configuración
  del ciclo de vida del `QTabWidget` mediante `configure_tab_widget()`.
- `navbar.py`: barra de navegación, conversión de direcciones y guardado de
  páginas.
- `web_profiles.py`: creación de perfiles aislados de Qt WebEngine. Usa un
  User-Agent compatible con WhatsApp tanto en JavaScript como en las cabeceras
  de red, y aplica el reemplazo por host mediante un interceptor;
  `build_web_profile(..., site_user_agents=...)` permite reemplazar ese mapa.
- `session.py`: restauración, metadatos y persistencia de sesiones.
- `local_viewer.py` y `folder_viewer.py`: archivos locales, carpetas,
  edición, Git y navegación dentro de archivos comprimidos. `archive_entries()`
  lista contenidos y `extract_archive()` extrae ZIP, TAR/GZIP/BZIP2 y, cuando
  están instaladas sus dependencias opcionales, RAR/7z.
- `video_tab.py` y `epub_tab.py`: visores locales; `video_tab.py` también
  expone `open_video_tab()` para crear y registrar una pestaña de video.
- `history.py`: persistencia SQLite y diálogo del historial agrupado por
  sesión de navegación.
- `sidebar.py` y `downloader_handoff.py`: paneles compartidos y entrega de
  descargas al Downloader.
- `sidebar.py` conserva los favicon de las aplicaciones en el campo `favicon`
  de cada entrada. Conectá `SidebarRail.on_favicon_changed` a
  `JsonListStore.update_item` para guardar el valor en disco.
- `navigation.py`: ajuste y restablecimiento del zoom de la vista activa,
  pestaña activa, activación de la pestaña `+`, sincronización
  de la barra de dirección y carga de URLs con callbacks específicos.
- `tabs.py`: `BLOCKED_URLS` contiene prefijos de URLs que no deben navegar ni
  abrir pestañas nuevas; agregá nuevos destinos bloqueados a esa lista.
- `assets/epub_reader.html`, `epub_reader.css` y `epub_reader.js`: plantilla
  y comportamiento del lector EPUB, separados del código Python.
- `assets/local_viewer.html`, `local_viewer.css`, `archive_viewer.html`,
  `archive_viewer.css` y `archive_viewer.js`: plantillas y recursos para
  mensajes locales y listados de comprimidos.
- `assets/folder_viewer.html`, `folder_viewer.css` y `folder_viewer.js`:
  plantilla, estilos y comportamiento del explorador de carpetas y archivos.
- `tabs.py` también expone `close_tab()`, que centraliza el cierre seguro,
  selección de la pestaña anterior y recreación de una pestaña cuando solo
  queda `+`; cada aplicación inyecta su limpieza particular.
- `local_file_types.py`: clasificación de extensiones locales. Mantiene esta
  decisión fuera de `folder_viewer.py` para que las pestañas WebEngine no
  dependan del explorador/editor de carpetas.

`downloader_handoff.py` también expone el handoff explícito de una URL actual.
Las ventanas pueden conectarlo a su barra sin interceptar navegación normal.

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

Los módulos se importan desde su responsabilidad concreta: `video_tab.py`
contiene tanto `VideoTab` como `open_video_tab()`, y `local_file_types.py`
contiene la clasificación de archivos de texto. `MiniBrowser` y `WebAgent` usan esas
ubicaciones directamente, sin módulos intermediarios de compatibilidad.
