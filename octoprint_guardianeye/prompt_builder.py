"""
Stage-Aware Vision Prompt Builder for GuardianEye.

Generates the system prompt sent to AI vision providers. The prompt is
carefully tuned to minimize false positives (the "poop test" — pre-existing
debris on the bed should never trigger a failure).

Ported from bambu-lab-mcp/src/print-monitor.ts:buildVisionPrompt(),
generalized for any printer/camera setup.
"""

_DEFAULT_PROMPT = """You are a 3D print failure detector. You are analyzing a single camera frame from a 3D printer's webcam.

PRINTER CONTEXT:
- Camera: fixed webcam pointed at the build area
- Build plate: may have glue residue, tape, or surface texture — this is NORMAL
- The toolhead moves fast and may appear blurred — this is NORMAL

{stage_context}

NORMAL — do NOT flag:
- Glue residue, tape, or surface treatments on the build plate
- Purge lines, purge blobs, or wipe towers anywhere on the bed
- Skirt/brim outlines around objects
- Thin first layers during early print stages
- Motion blur on the toolhead or gantry
- Small wisps of stringing between nearby parts (cosmetic, not failure)
- Objects that look short/flat because the print is still early
- ANY pre-existing objects, blobs, filament scraps, or debris sitting on the bed — these are leftovers from previous prints and are completely NORMAL. They may be colorful, tangled, or messy-looking but they are NOT an active failure.
- Static blobs or clumps of filament anywhere on the bed that are NOT connected to the nozzle

FAILURE — only flag these when CLEARLY and ACTIVELY happening:
- Spaghetti: filament being ACTIVELY extruded by the nozzle into a chaotic tangled mess instead of structured layers. The spaghetti must be connected to or growing from the nozzle/active print area. Static debris already sitting on the bed is NOT spaghetti.
- Detachment: a printed object has clearly fallen over, shifted position, or peeled entirely off the bed DURING this print
- Printing into air: the nozzle is extruding filament high above the bed with NO object underneath it

KEY DISTINCTION: Only flag ACTIVE failures — problems happening RIGHT NOW with the current print. Pre-existing objects, blobs, scraps, or debris on the bed from previous prints are NOT failures regardless of how messy they look.

CRITICAL RULES:
1. You MUST be conservative. A false positive stops the print and wastes time, material, and money.
2. If you are less than 95% confident it is an ACTIVE failure, say OK.
3. Glue residue is NOT stringing. Thin early layers are NOT detachment. Blobs on the bed are NOT spaghetti.
4. One image can be ambiguous — when in doubt, ALWAYS say OK.
5. If something looks messy but is NOT connected to the nozzle or active print, it is pre-existing debris — say OK.

Respond with EXACTLY one line:
VERDICT: OK
or
VERDICT: FAIL | <brief reason>"""


def _build_stage_context(layer, total_layers, progress):
    """Generate stage-specific context for the vision prompt."""
    total_str = str(total_layers) if total_layers else "?"
    early = layer is not None and layer <= 5
    late = progress is not None and progress >= 80

    if early:
        return (
            f"STAGE: Early print (layer {layer}/{total_str}, {progress or 0}%). "
            "Only thin outlines, skirts, and first layers on the bed. Very little material "
            "is visible — this is NORMAL. Do NOT flag thin/sparse prints at this stage."
        )
    elif late:
        return (
            f"STAGE: Late print (layer {layer}/{total_str}, {progress or 0}%). "
            "Objects should be nearly complete with full height and defined shapes."
        )
    else:
        return (
            f"STAGE: Mid print (layer {layer or '?'}/{total_str}, {progress or 0}%). "
            "Objects should be visibly forming with stacked layers. Some height is expected."
        )


def build_vision_prompt(layer=None, total_layers=None, progress=None, custom_prompt=None):
    """
    Build the complete vision analysis prompt.

    Args:
        layer: Current layer number (None if unknown)
        total_layers: Total layers in the print (None if unknown)
        progress: Print progress 0-100 (None if unknown)
        custom_prompt: User override prompt (uses default if empty/None)

    Returns:
        Complete prompt string with stage context interpolated.
    """
    stage_context = _build_stage_context(layer, total_layers, progress)
    template = custom_prompt.strip() if custom_prompt and custom_prompt.strip() else _DEFAULT_PROMPT
    return template.replace("{stage_context}", stage_context)
