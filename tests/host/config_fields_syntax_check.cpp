// tests/host/config_fields_syntax_check.cpp -- a translation unit whose
// only job is to give test_cxx11_syntax_gate.py something to compile
// for src/comms/config_fields.h, which is host-portable (it holds the
// wire's config-name table and nothing that touches pxt.h) but has no
// natural .cpp of its own. The header is also reached transitively by
// wire_adapter.cpp, already in that gate; this unit makes the coverage
// explicit and independent of who happens to include it.

#include "comms/config_fields.h"

const diffDrive::ConfigFieldDescriptor* configFieldsSyntaxCheckByName() {
  return diffDrive::findConfigField("v_max");
}

const diffDrive::ConfigFieldDescriptor* configFieldsSyntaxCheckByOrdinal() {
  return diffDrive::findConfigFieldByOrdinal(21);
}

int configFieldsSyntaxCheckCount() { return diffDrive::kConfigFieldCount; }
