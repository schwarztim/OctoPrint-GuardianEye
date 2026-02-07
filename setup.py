from setuptools import setup

plugin_identifier = "guardianeye"
plugin_package = "octoprint_guardianeye"
plugin_name = "OctoPrint-GuardianEye"
plugin_version = "1.0.0"
plugin_description = "AI-powered print failure detection using camera snapshots. Supports OpenAI, Azure OpenAI, Anthropic, xAI/Grok, Google Gemini, and Ollama."
plugin_author = "Tim Schwarz"
plugin_author_email = "schwarztim@users.noreply.github.com"
plugin_url = "https://github.com/schwarztim/OctoPrint-GuardianEye"
plugin_license = "AGPLv3"
plugin_additional_data = []

plugin_requires = ["requests>=2.28.0"]
plugin_extra_requires = {}
plugin_additional_packages = []
plugin_ignored_packages = []

additional_setup_parameters = {
    "python_requires": ">=3.7,<4",
}

try:
    import octoprint_setuptools
except ImportError:
    import sys
    print(
        "Could not import OctoPrint's setuptools, are you sure you are running that under the same python installation that OctoPrint is installed under?"
    )
    sys.exit(-1)

setup_parameters = octoprint_setuptools.create_plugin_setup_parameters(
    identifier=plugin_identifier,
    package=plugin_package,
    name=plugin_name,
    version=plugin_version,
    description=plugin_description,
    author=plugin_author,
    mail=plugin_author_email,
    url=plugin_url,
    license=plugin_license,
    requires=plugin_requires,
    extra_requires=plugin_extra_requires,
    additional_packages=plugin_additional_packages,
    ignored_packages=plugin_ignored_packages,
    additional_data=plugin_additional_data,
)

if len(googled := additional_setup_parameters):
    setup_parameters.update(googled)

setup(**setup_parameters)
