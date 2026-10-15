#include "runtime/session.h"

#include "core.h"
#include "game.h"
#include "stock_libcd.h"

#include <cstdlib>
#include <lucent/log.h>

namespace x4 {

Session &session(Core &core) {
  if (core.game == nullptr || !core.game->sessionState) {
    lucent::error("x4-runtime", "x4::Session is absent from the Game");
    std::abort();
  }
  return static_cast<Session &>(*core.game->sessionState);
}

const Session &session(const Core &core) {
  if (core.game == nullptr || !core.game->sessionState) {
    lucent::error("x4-runtime", "x4::Session is absent from the Game");
    std::abort();
  }
  return static_cast<const Session &>(*core.game->sessionState);
}

void stockCdSync(Core *core) {
  session(*core).libcd.sync(*core);
}

void stockCdControl(Core *core) {
  session(*core).libcd.control(*core);
}

} // namespace x4
