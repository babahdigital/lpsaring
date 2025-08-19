# backend/app/infrastructure/api_docs/__init__.py
"""
API Documentation setup using flask-swagger-ui and apispec
"""

from flask import Blueprint, jsonify, url_for, current_app
from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from apispec_webframeworks.flask import FlaskPlugin
from flask_swagger_ui import get_swaggerui_blueprint

def create_api_docs(app):
    """
    Set up API documentation with Swagger UI
    
    Args:
        app: Flask application instance
    """
    # Create API spec
    spec = APISpec(
        title="Hotspot Portal API",
        version="1.0.0",
        openapi_version="3.0.2",
        plugins=[FlaskPlugin(), MarshmallowPlugin()],
        info={
            "description": "API documentation for the Hotspot Portal",
            "contact": {"email": "admin@sobigidul.com"}
        },
    )
    
    # Daftarkan semua skema Pydantic dan Marshmallow
    from app.infrastructure.http.schemas import auth_schemas, device_schemas, user_schemas
    
    # Fungsi untuk mendaftarkan skema Pydantic dari modul
    def register_pydantic_schemas(module):
        for name, obj in vars(module).items():
            # Handle Pydantic v2 models
            if hasattr(obj, 'model_json_schema'):
                try:
                    schema_dict = obj.model_json_schema()
                    spec.components.schema(name, schema_dict)
                    app.logger.debug(f"Registered Pydantic schema: {name}")
                except Exception as e:
                    app.logger.warning(f"Error registering schema {name}: {e}")
            # Handle Pydantic v1 models (untuk kompatibilitas)
            elif hasattr(obj, 'schema'):
                try:
                    schema_dict = obj.schema()
                    spec.components.schema(name, schema_dict)
                    app.logger.debug(f"Registered Pydantic v1 schema: {name}")
                except Exception as e:
                    app.logger.warning(f"Error registering schema {name}: {e}")
    
    # Register semua skema dari modul yang berbeda
    app.logger.info("Registering API schemas...")
    modules_to_register = [auth_schemas, device_schemas, user_schemas]
    
    for module in modules_to_register:
        register_pydantic_schemas(module)
    
    # Register blueprints and extract paths from the app's routes
    with app.test_request_context():
        # Get list of all registered routes
        for rule in app.url_map.iter_rules():
            if rule.endpoint != 'static' and not rule.rule.startswith('/swagger'):
                try:
                    # Extract view function
                    view_func = app.view_functions[rule.endpoint]
                    
                    # Document view function if it has a docstring
                    if view_func.__doc__:
                        import yaml
                        from inspect import getdoc
                        
                        docstring = getdoc(view_func)
                        methods = [m.lower() for m in rule.methods if m not in ['HEAD', 'OPTIONS']]
                        
                        # Coba parse YAML jika ada format YAML
                        if docstring and '---' in docstring:
                            app.logger.debug(f"Found YAML docstring in {rule.endpoint}")
                            yaml_part = docstring.split('---', 1)[1]
                            
                            try:
                                yaml_dict = yaml.safe_load(yaml_part)
                                
                                if isinstance(yaml_dict, dict):
                                    # Jika format YAML lengkap dengan metode HTTP sebagai kunci
                                    if any(method in yaml_dict for method in methods):
                                        app.logger.debug(f"Using full YAML spec for {rule.rule}")
                                        spec.path(path=rule.rule, operations=yaml_dict)
                                    # Format YAML tanpa metode HTTP (gunakan untuk semua metode)
                                    else:
                                        app.logger.debug(f"Using shared YAML spec for all methods in {rule.rule}")
                                        operations = {}
                                        for method in methods:
                                            operations[method] = yaml_dict
                                        spec.path(path=rule.rule, operations=operations)
                                    continue  # Lanjutkan ke rule berikutnya
                                else:
                                    app.logger.warning(f"Invalid YAML structure for {rule.endpoint}: not a dict")
                            except yaml.YAMLError as e:
                                app.logger.error(f"Error parsing YAML in {rule.endpoint}: {e}")
                        
                        # Fallback ke metode sederhana
                        app.logger.debug(f"Using simple documentation for {rule.rule}")
                        operations = {}
                        for method in methods:
                            # Ekstrak deskripsi singkat dari baris pertama docstring
                            description = docstring.split("\n")[0] if docstring else "No description"
                            operations[method] = {
                                "summary": description,
                                "description": docstring
                            }
                        
                        spec.path(path=rule.rule, operations=operations)
                except (AssertionError, KeyError, Exception) as e:
                    # Skip routes that can't be properly documented
                    if not app.config.get('SUPPRESS_API_DOCS_SKIP_LOG', False):
                        app.logger.debug(f"Skipping route {rule.rule}: {str(e)}")
    
    # Create a blueprint for serving the API spec
    docs_bp = Blueprint('api_docs', __name__, url_prefix='/api/docs')
    
    @docs_bp.route('/swagger.json')
    def swagger_json():
        """Serve the API specification as JSON"""
        spec_dict = spec.to_dict()
        
        # Export spec to file for offline use
        try:
            import os
            import json
            
            output_dir = os.path.join(os.path.dirname(app.root_path), '.output')
            os.makedirs(output_dir, exist_ok=True)
            
            output_path = os.path.join(output_dir, 'swagger.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(spec_dict, f, indent=2)
                
            app.logger.info(f"OpenAPI spec exported to {output_path}")
        except Exception as e:
            app.logger.error(f"Failed to export OpenAPI spec: {e}")
        
        return jsonify(spec_dict)
    
    # Register the docs blueprint
    app.register_blueprint(docs_bp)
    
    # Create and register Swagger UI blueprint
    swaggerui_blueprint = get_swaggerui_blueprint(
        '/api/swagger',
        '/api/docs/swagger.json',
        config={
            'app_name': "Hotspot Portal API",
            'dom_id': '#swagger-ui',
            'layout': 'BaseLayout',
            'deepLinking': True,
        }
    )
    
    app.register_blueprint(swaggerui_blueprint, url_prefix='/api/swagger')
    
    # Log information about documented routes and schemas
    route_count = len([rule for rule in app.url_map.iter_rules() 
                      if rule.endpoint != 'static' and not rule.rule.startswith('/swagger')])
    schema_count = len(spec.components.schemas)
    
    app.logger.info(f"API Documentation setup complete.")
    app.logger.info(f"- Documented {route_count} routes")
    app.logger.info(f"- Registered {schema_count} schemas")
    app.logger.info(f"- Swagger UI available at: /api/swagger")
    app.logger.info(f"- OpenAPI JSON available at: /api/docs/swagger.json")
    
    return app
