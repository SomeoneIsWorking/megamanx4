#pragma once

#include "guest_widescreen_projection.h"

class Core;

namespace x4 {

// Process-lifetime policy. It declares the requested presentation aspect; the per-Core controller
// below owns the matching guest projection and draw-environment publications.
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

  // These are the production transformations as well as the narrow falsifier seam. The injected
  // body is always the authenticated original guest function executed through Lightrec.
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
