#pragma once

#include "guest_widescreen_projection.h"

class Core;

namespace x4 {

// Process-lifetime policy declaring the requested aspect.
class WidescreenPolicy final : public GuestWidescreenProjection {
public:
  PresentationAspect presentationAspect(const Core &core) const override;
};

class WidescreenController {
public:
  using GuestBody = void (*)(Core *);
  using ProjectionLatch = GuestProjectionPlan (*)(Core *, GuestProjectionGeometry);

  WidescreenController();
  explicit WidescreenController(ProjectionLatch latch);

  // retailBody is the original guest function run through Lightrec.
  void publishProjection(Core &core, GuestBody retailBody);
  void publishDrawEnvironment(Core &core, GuestBody retailBody);
  void synchronizePresentation(Core &core);

  const GuestProjectionPlan &plan() const {
    return plan_;
  }

private:
  ProjectionLatch latch_;
  GuestProjectionPlan plan_;
  bool projectionPublished_ = false;
};

} // namespace x4
