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
                        spec.path(path=rule.rule, operations={"get": {"description": view_func.__doc__}})
                except (AssertionError, KeyError, Exception) as e:
                    # Skip routes that can't be properly documented
                    if not app.config.get('SUPPRESS_API_DOCS_SKIP_LOG', False):
                        app.logger.debug(f"Skipping route {rule.rule}: {str(e)}")
    
    # Create a blueprint for serving the API spec
    docs_bp = Blueprint('api_docs', __name__, url_prefix='/api/docs')
    
    @docs_bp.route('/swagger.json')
    def swagger_json():
        """Serve the API specification as JSON"""
        return jsonify(spec.to_dict())
    
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
    
    return app
