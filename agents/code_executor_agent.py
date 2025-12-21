"""
CodeExecutorAgent: Compiles and executes generated Java initialization code.
"""

import os
import re
import json
import subprocess
import tempfile
from typing import Dict, Any, List, Optional

from config import CLASS_PATH


class CodeExecutorAgent:
    """
    Agent responsible for compiling and running Java code, then extracting
    JSON output from stdout.
    """

    def __init__(self, classpath: str = "", jdk_home: Optional[str] = None):
        """
        Initialize the code executor.

        Args:
            classpath: Classpath to use for compilation and execution (colon-separated on Linux).
            jdk_home: Optional path to JDK installation (defaults to JAVA_HOME or system java).
        """
        # If not provided, fall back to CLASS_PATH from config (comma-separated), normalized for OS
        self.classpath = classpath or self._normalize_classpath(CLASS_PATH)
        self.jdk_home = jdk_home or os.environ.get("JAVA_HOME", "")

    def _get_java_executable(self, tool: str) -> str:
        """Get the path to javac or java executable."""
        if self.jdk_home:
            return os.path.join(self.jdk_home, "bin", tool)
        return tool  # Assume it's in PATH

    def compile_and_execute(
        self, java_code: str, class_name: str = "InitializerMain"
    ) -> Dict[str, Any]:
        """
        Compile and execute the provided Java code, capturing JSON output.

        Args:
            java_code: The full Java source code to compile and run.
            class_name: The main class name (default: InitializerMain).

        Returns:
            Dict with:
                - success: bool (True if execution succeeded)
                - objects: List of parsed JSON objects from stdout
                - compile_output: str (stdout/stderr from javac)
                - run_output: str (stdout from java)
                - run_error: str (stderr from java)
                - error: str (error message if any)
        """
        result = {
            "success": False,
            "objects": [],
            "compile_output": "",
            "run_output": "",
            "run_error": "",
            "error": "",
        }

        # Create a temporary directory for the Java file
        with tempfile.TemporaryDirectory() as tmpdir:
            # If the code declares a public class, use that as the filename/entrypoint
            detected_class = self._detect_public_class_name(java_code)
            if detected_class:
                class_name = detected_class

            # Write the Java code to a file
            java_file = os.path.join(tmpdir, f"{class_name}.java")
            try:
                with open(java_file, "w", encoding="utf-8") as f:
                    f.write(java_code)
            except Exception as e:
                result["error"] = f"Failed to write Java file: {e}"
                return result

            # Compile the Java code
            javac_cmd = [self._get_java_executable("javac")]
            if self.classpath:
                javac_cmd.extend(["-cp", self.classpath])
            javac_cmd.append(java_file)

            try:
                compile_proc = subprocess.run(
                    javac_cmd,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                result["compile_output"] = compile_proc.stdout + compile_proc.stderr

                if compile_proc.returncode != 0:
                    result["error"] = f"Compilation failed: {result['compile_output']}"
                    return result
            except subprocess.TimeoutExpired:
                result["error"] = "Compilation timed out"
                return result
            except Exception as e:
                result["error"] = f"Compilation error: {e}"
                return result

            # Run the compiled Java code
            java_cmd = [self._get_java_executable("java")]
            if self.classpath:
                # Include both the classpath and the tmpdir for the compiled class
                combined_cp = f"{tmpdir}{os.pathsep}{self.classpath}"
                java_cmd.extend(["-cp", combined_cp])
            else:
                java_cmd.extend(["-cp", tmpdir])
            java_cmd.append(class_name)

            try:
                run_proc = subprocess.run(
                    java_cmd,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                result["run_output"] = run_proc.stdout
                result["run_error"] = run_proc.stderr

                if run_proc.returncode != 0:
                    result["error"] = f"Execution failed (exit code {run_proc.returncode}): {result['run_error']}"
                    return result
            except subprocess.TimeoutExpired:
                result["error"] = "Execution timed out"
                return result
            except Exception as e:
                result["error"] = f"Execution error: {e}"
                return result

            # Parse JSON objects from stdout
            objects = self._extract_json_objects(result["run_output"])
            result["objects"] = objects
            result["success"] = True

        return result

    def _extract_json_objects(self, stdout: str) -> List[Dict[str, Any]]:
        """
        Extract JSON objects from stdout.

        Looks for lines containing JSON objects (starting with '{' and ending with '}').
        Supports two formats:
        1. New format: {"variable": "<var_name>", "object": <json_object>}
        2. Legacy format: <json_object> (for backward compatibility)
        """
        objects = []
        lines = stdout.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line or not (line.startswith("{") and line.endswith("}")):
                continue
            try:
                obj = json.loads(line)
                # Check if it's the new format with variable mapping
                if "variable" in obj and "object" in obj:
                    # New format: extract the variable name and object
                    objects.append({
                        "variable": obj["variable"],
                        "object": obj["object"],
                    })
                else:
                    # Legacy format: just the object itself
                    objects.append(obj)
            except json.JSONDecodeError:
                # Skip lines that aren't valid JSON
                continue

        return objects

    def _normalize_classpath(self, raw_cp: str) -> str:
        """Normalize a comma-separated or os.pathsep-separated classpath from config."""
        if not raw_cp:
            return ""
        parts: List[str] = []
        # Replace commas with os.pathsep, then split
        for token in raw_cp.replace(',', os.pathsep).split(os.pathsep):
            token = token.strip()
            if not token:
                continue
            if token not in parts:
                parts.append(token)
        return os.pathsep.join(parts)

    def _detect_public_class_name(self, java_code: str) -> Optional[str]:
        """Detect a public class name to align filename/entrypoint with Java conventions."""
        # Simple regex to find `public class X` or `public final class X`
        m = re.search(r"public\s+(?:final\s+)?class\s+(\w+)", java_code)
        if m:
            return m.group(1)
        return None
