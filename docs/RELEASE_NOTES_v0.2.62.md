# CANCHERIA v0.2.62

## Logo personalizable

- El logo del encabezado principal ahora abre un menú contextual con clic derecho.
- **Cambiar logo** permite elegir imágenes PNG, JPG, JPEG, GIF, BMP o WebP y las normaliza de forma segura para la interfaz.
- **Restablecer logo original** elimina solamente la personalización y vuelve al logo incluido con CANCHERIA.
- El logo personalizado se guarda dentro de `runtime`, por lo que persiste después de reiniciar o actualizar la aplicación.
- Una imagen inválida no reemplaza el logo actual y muestra un error claro al usuario.

## Verificación

- Se añadieron pruebas para el contrato visual del menú contextual y para la normalización persistente de imágenes.
- La carpeta `runtime` continúa protegida por el sistema de actualización y respaldo.
