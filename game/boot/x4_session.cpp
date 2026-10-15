#include "x4_session.h"

#include "core.h"
#include "game.h"
#include "stock_libcd.h"

#include <cstdlib>
#include <lucent/log.h>

namespace x4 {

X4Session &session(Core &core) {
  if (core.game == nullptr || !core.game->sessionState) {
    lucent::error("x4-runtime", "X4Session is absent from the Game");
    std::abort();
  }
  return static_cast<X4Session &>(*core.game->sessionState);
}

const X4Session &session(const Core &core) {
  if (core.game == nullptr || !core.game->sessionState) {
    lucent::error("x4-runtime", "X4Session is absent from the Game");
    std::abort();
  }
  return static_cast<const X4Session &>(*core.game->sessionState);
}

void stockCdSync(Core *core) {
  session(*core).libcd.sync(*core);
}

void stockCdControl(Core *core) {
  session(*core).libcd.control(*core);
}

} // namespace x4
