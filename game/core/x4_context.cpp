#include "x4_context.h"

#include "core.h"

#include <cstdlib>
#include <lucent/log.h>

namespace x4 {

X4Context &context(Core &core) {
  if (!core.gameCtx) {
    lucent::error("x4-runtime", "X4Context is absent from Core");
    std::abort();
  }
  return *static_cast<X4Context *>(core.gameCtx);
}

const X4Context &context(const Core &core) {
  if (!core.gameCtx) {
    lucent::error("x4-runtime", "X4Context is absent from Core");
    std::abort();
  }
  return *static_cast<const X4Context *>(core.gameCtx);
}

} // namespace x4
